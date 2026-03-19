-- PostgreSQL schema translated from schema.sql (SQLite)
-- Changes: TIMESTAMP → TIMESTAMPTZ, REAL → DOUBLE PRECISION,
--          INTEGER booleans → BOOLEAN, DROP TABLE ... CASCADE before each CREATE

-- Drop tables in reverse dependency order
DROP TABLE IF EXISTS agent_executions CASCADE;
DROP TABLE IF EXISTS call_messages_log CASCADE;
DROP TABLE IF EXISTS intents CASCADE;
DROP TABLE IF EXISTS user_preferences CASCADE;
DROP TABLE IF EXISTS call_sessions CASCADE;
DROP TABLE IF EXISTS terminal_logs CASCADE;
DROP TABLE IF EXISTS terminal_commands CASCADE;
DROP TABLE IF EXISTS terminal_sessions CASCADE;
DROP TABLE IF EXISTS agent_tokens CASCADE;
DROP TABLE IF EXISTS instances CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS projects CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- 1. USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    phone_number TEXT UNIQUE,
    pin_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. PROJECTS TABLE
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    file_path TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    last_accessed TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 3. TASKS TABLE
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,

    voice_command TEXT,
    description TEXT NOT NULL,

    output_summary TEXT,

    intent_type TEXT,
    intent_confidence DOUBLE PRECISION,
    raw_transcript TEXT,

    status TEXT DEFAULT 'pending',
    assigned_to_claude_instance TEXT,
    terminal_session_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 4. INSTANCES TABLE
CREATE TABLE IF NOT EXISTS instances (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    project_id TEXT NOT NULL,
    pid INTEGER,
    instance_token TEXT,
    metadata TEXT,
    status TEXT DEFAULT 'starting',
    last_heartbeat TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- 4a. AGENT TOKENS
CREATE TABLE IF NOT EXISTS agent_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    label TEXT,
    token_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 4b. TERMINAL SESSIONS
CREATE TABLE IF NOT EXISTS terminal_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    instance_id TEXT,
    name TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    closed_at TIMESTAMPTZ,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (instance_id) REFERENCES instances(id)
);

-- 4c. TERMINAL COMMANDS
CREATE TABLE IF NOT EXISTS terminal_commands (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    command TEXT NOT NULL,
    status TEXT DEFAULT 'queued',
    exit_code INTEGER,
    created_at TIMESTAMPTZ DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    FOREIGN KEY (session_id) REFERENCES terminal_sessions(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 4d. TERMINAL LOGS
CREATE TABLE IF NOT EXISTS terminal_logs (
    id TEXT PRIMARY KEY,
    command_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    stream TEXT NOT NULL,
    chunk TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (command_id) REFERENCES terminal_commands(id)
);

-- 5. CALL SESSIONS TABLE
CREATE TABLE IF NOT EXISTS call_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    phone_number TEXT,
    twilio_call_sid TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at TIMESTAMPTZ,
    transcript TEXT,
    commands_executed TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 6. USER PREFERENCES
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    phone_number TEXT,
    default_project TEXT,
    voice_speed TEXT DEFAULT 'normal',
    email_notifications BOOLEAN DEFAULT true,
    sms_notifications BOOLEAN DEFAULT false,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 7. INTENTS
CREATE TABLE IF NOT EXISTS intents (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    intent_type TEXT NOT NULL,
    confidence DOUBLE PRECISION,
    raw_transcript TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- 7b. CALL MESSAGES LOG
CREATE TABLE IF NOT EXISTS call_messages_log (
    id TEXT PRIMARY KEY,
    call_session_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    message TEXT NOT NULL,
    intent_detected TEXT,
    timestamp TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (call_session_id) REFERENCES call_sessions(id)
);

-- 8. AGENT EXECUTIONS TABLE
CREATE TABLE IF NOT EXISTS agent_executions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    input_prompt TEXT,
    refined_prompt TEXT,
    output_result TEXT,
    explanation TEXT,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    execution_time_ms INTEGER,
    terminal_command_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- Indexes for dashboard queries
CREATE INDEX IF NOT EXISTS idx_projects_user_last_accessed ON projects(user_id, last_accessed);
CREATE INDEX IF NOT EXISTS idx_tasks_user_created_at ON tasks(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_project_created_at ON tasks(project_id, created_at);

-- Indexes for terminal queries
CREATE INDEX IF NOT EXISTS idx_instances_project_heartbeat ON instances(project_id, last_heartbeat);
CREATE INDEX IF NOT EXISTS idx_agent_tokens_user_created ON agent_tokens(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_terminal_sessions_user_project ON terminal_sessions(user_id, project_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_terminal_commands_session_created ON terminal_commands(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_terminal_logs_command_sequence ON terminal_logs(command_id, sequence);

-- ============================================================
-- RPC FUNCTIONS
-- ============================================================

-- Function 1: get_user_projects_with_task_counts
CREATE OR REPLACE FUNCTION get_user_projects_with_task_counts(p_user_id TEXT)
RETURNS TABLE (
  id TEXT, name TEXT, status TEXT,
  total_tasks BIGINT, pending_tasks BIGINT,
  in_progress_tasks BIGINT, completed_tasks BIGINT
) AS $$
  SELECT
    p.id, p.name, p.status,
    COUNT(t.id) as total_tasks,
    COALESCE(SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END), 0) as pending_tasks,
    COALESCE(SUM(CASE WHEN t.status = 'in_progress' THEN 1 ELSE 0 END), 0) as in_progress_tasks,
    COALESCE(SUM(CASE WHEN t.status IN ('completed', 'agent_completed') THEN 1 ELSE 0 END), 0) as completed_tasks
  FROM projects p
  LEFT JOIN tasks t ON p.id = t.project_id
  WHERE p.user_id = p_user_id
  GROUP BY p.id, p.name, p.status, p.last_accessed
  ORDER BY p.last_accessed DESC;
$$ LANGUAGE sql STABLE;

-- Function 2: claim_next_queued_command
CREATE OR REPLACE FUNCTION claim_next_queued_command(p_instance_id TEXT)
RETURNS SETOF terminal_commands AS $$
DECLARE
  v_command_id TEXT;
BEGIN
  SELECT tc.id INTO v_command_id
  FROM terminal_commands tc
  JOIN terminal_sessions ts ON ts.id = tc.session_id
  WHERE ts.instance_id = p_instance_id
    AND tc.status = 'queued'
  ORDER BY tc.created_at ASC
  LIMIT 1
  FOR UPDATE OF tc SKIP LOCKED;

  IF v_command_id IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  UPDATE terminal_commands
  SET status = 'running', started_at = now()
  WHERE id = v_command_id AND status = 'queued'
  RETURNING *;
END;
$$ LANGUAGE plpgsql;

-- Function 3: delete_user_history
CREATE OR REPLACE FUNCTION delete_user_history(p_user_id TEXT)
RETURNS JSONB AS $$
DECLARE
  counts JSONB := '{}'::JSONB;
  c BIGINT;
BEGIN
  -- terminal_logs via commands
  SELECT COUNT(*) INTO c FROM terminal_logs tl JOIN terminal_commands tc ON tc.id = tl.command_id WHERE tc.user_id = p_user_id;
  counts := counts || jsonb_build_object('terminal_logs', c);
  DELETE FROM terminal_logs WHERE command_id IN (SELECT id FROM terminal_commands WHERE user_id = p_user_id);

  SELECT COUNT(*) INTO c FROM terminal_commands WHERE user_id = p_user_id;
  counts := counts || jsonb_build_object('terminal_commands', c);
  DELETE FROM terminal_commands WHERE user_id = p_user_id;

  SELECT COUNT(*) INTO c FROM terminal_sessions WHERE user_id = p_user_id;
  counts := counts || jsonb_build_object('terminal_sessions', c);
  DELETE FROM terminal_sessions WHERE user_id = p_user_id;

  -- agent_executions via tasks
  SELECT COUNT(*) INTO c FROM agent_executions ae JOIN tasks t ON t.id = ae.task_id WHERE t.user_id = p_user_id;
  counts := counts || jsonb_build_object('agent_executions', c);
  DELETE FROM agent_executions WHERE task_id IN (SELECT id FROM tasks WHERE user_id = p_user_id);

  SELECT COUNT(*) INTO c FROM intents i JOIN tasks t ON t.id = i.task_id WHERE t.user_id = p_user_id;
  counts := counts || jsonb_build_object('intents', c);
  DELETE FROM intents WHERE task_id IN (SELECT id FROM tasks WHERE user_id = p_user_id);

  SELECT COUNT(*) INTO c FROM tasks WHERE user_id = p_user_id;
  counts := counts || jsonb_build_object('tasks', c);
  DELETE FROM tasks WHERE user_id = p_user_id;

  -- call messages via sessions
  SELECT COUNT(*) INTO c FROM call_messages_log cml JOIN call_sessions cs ON cs.id = cml.call_session_id WHERE cs.user_id = p_user_id;
  counts := counts || jsonb_build_object('call_messages_log', c);
  DELETE FROM call_messages_log WHERE call_session_id IN (SELECT id FROM call_sessions WHERE user_id = p_user_id);

  SELECT COUNT(*) INTO c FROM call_sessions WHERE user_id = p_user_id;
  counts := counts || jsonb_build_object('call_sessions', c);
  DELETE FROM call_sessions WHERE user_id = p_user_id;

  SELECT COUNT(*) INTO c FROM instances WHERE user_id = p_user_id;
  counts := counts || jsonb_build_object('instances', c);
  DELETE FROM instances WHERE user_id = p_user_id;

  RETURN counts;
END;
$$ LANGUAGE plpgsql;
