-- 1. USERS TABLE (New: Required for SRS FR-6.1 Security)
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    phone_number TEXT UNIQUE,
    pin_hash TEXT, -- Store bcrypt hash of the 4-6 digit PIN
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. PROJECTS TABLE (Updated)
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT, -- Added per SRS 6.1
    file_path TEXT,   -- Local path on developer's machine
    status TEXT DEFAULT 'active', -- 'active', 'archived'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 3. TASKS TABLE (Updated: include user_id for simpler per-user queries)
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,

    voice_command TEXT,      -- What the user actually said (SRS FR-5.2)
    description TEXT NOT NULL, -- The parsed intent/description

    output_summary TEXT,     -- What Claude actually did (SRS FR-5.2)

    intent_type TEXT,          -- e.g., 'create_file', 'run_command', 'search_web'
    intent_confidence REAL,       -- Confidence score from NLP parsing (0.0 - 1.0)
    raw_transcript TEXT,        -- Full transcript of the voice command

    status TEXT DEFAULT 'pending', -- 'pending', 'in_progress', 'completed', 'failed'
    assigned_to_claude_instance TEXT,
    terminal_session_id TEXT,      -- link to terminal_sessions if this task uses a session
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 4. INSTANCES TABLE (New: Required for SRS FR-2.1 Orchestration)
CREATE TABLE IF NOT EXISTS instances (
    id TEXT PRIMARY KEY,
    user_id TEXT,            -- Supabase user id (for multi-tenant SaaS)
    project_id TEXT NOT NULL,
    pid INTEGER,             -- Process ID on local machine
    instance_token TEXT,     -- Token reported by local helper (stable across restarts)
    metadata TEXT,           -- JSON blob (machine info, capabilities)
    status TEXT DEFAULT 'starting', -- 'starting', 'online', 'offline', 'error'
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- 4a. AGENT TOKENS (pair local agent without requiring Supabase JWT)
CREATE TABLE IF NOT EXISTS agent_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    label TEXT,
    token_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    revoked_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 4b. TERMINAL SESSIONS (local-machine terminal sessions per project/user)
CREATE TABLE IF NOT EXISTS terminal_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    instance_id TEXT,        -- bound local helper instance (optional)
    name TEXT,
    status TEXT DEFAULT 'pending', -- 'pending', 'active', 'closing', 'closed', 'error'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (instance_id) REFERENCES instances(id)
);

-- 4c. TERMINAL COMMANDS (auditable command history)
CREATE TABLE IF NOT EXISTS terminal_commands (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    command TEXT NOT NULL,
    source TEXT DEFAULT 'typed', -- 'voice' | 'typed' | 'system'
    provider TEXT DEFAULT 'shell', -- 'cursor' | 'claude' | 'shell'
    user_prompt TEXT,
    normalized_command TEXT,
    status TEXT DEFAULT 'queued',  -- 'pending_approval', 'queued', 'running', 'completed', 'failed', 'cancelled'
    exit_code INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES terminal_sessions(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 4e. CONVERSATION TURNS (assistant/user thread shown in command center)
CREATE TABLE IF NOT EXISTS conversation_turns (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    project_id TEXT,
    session_id TEXT,
    command_id TEXT,
    role TEXT NOT NULL, -- 'assistant' | 'user' | 'system'
    turn_type TEXT NOT NULL, -- 'question' | 'reply' | 'approval_request' | 'approval_result' | 'info'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (session_id) REFERENCES terminal_sessions(id),
    FOREIGN KEY (command_id) REFERENCES terminal_commands(id)
);

-- 4f. CONVERSATION STATE (lightweight pending context per user+project)
CREATE TABLE IF NOT EXISTS conversation_state (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    project_id TEXT,
    active_command_id TEXT,
    state TEXT NOT NULL DEFAULT 'idle', -- 'idle' | 'awaiting_approval'
    context_json TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (active_command_id) REFERENCES terminal_commands(id)
);

-- 4d. TERMINAL LOGS (chunked stdout/stderr streaming, optional but useful for UI)
CREATE TABLE IF NOT EXISTS terminal_logs (
    id TEXT PRIMARY KEY,
    command_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    stream TEXT NOT NULL,    -- 'stdout' | 'stderr'
    chunk TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (command_id) REFERENCES terminal_commands(id)
);

-- 5. CALL SESSIONS TABLE (Updated)
CREATE TABLE IF NOT EXISTS call_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    phone_number TEXT,
    twilio_call_sid TEXT,    -- Useful for linking to Twilio logs later
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    transcript TEXT,
    commands_executed TEXT,  -- JSON list of task_ids created
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 6. USER PREFERENCES (Kept same)
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    phone_number TEXT,
    default_project TEXT,
    default_provider TEXT DEFAULT 'cursor',
    project_base_path TEXT, -- absolute folder where new projects should live on the user's machine
    terminal_access_granted INTEGER DEFAULT 0,
    voice_speed TEXT DEFAULT 'normal',
    email_notifications INTEGER DEFAULT 1,
    sms_notifications INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 6a. COMPANION DEVICES (desktop companion registrations)
CREATE TABLE IF NOT EXISTS companion_devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT,
    platform TEXT,
    status TEXT DEFAULT 'pending', -- 'pending' | 'online' | 'offline'
    pairing_code TEXT,
    pairing_expires_at TIMESTAMP,
    device_token_hash TEXT,
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 6b. DEVICE -> PROJECT LINKS
CREATE TABLE IF NOT EXISTS device_project_links (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    local_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES companion_devices(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- 6c. CURSOR CONTEXT SNAPSHOTS (from local extension)
CREATE TABLE IF NOT EXISTS cursor_context_snapshots (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    file_path TEXT,
    selection TEXT,
    diagnostics TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES companion_devices(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS intents (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    intent_type TEXT NOT NULL, -- e.g., 'create_file', 'run_command', 'search_web'
    confidence REAL,           -- Confidence score from NLP parsing (0.0 - 1.0)
    raw_transcript TEXT,      -- Full transcript of the voice command
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS call_messages_log (
    id TEXT PRIMARY KEY,
    call_session_id TEXT NOT NULL,
    sender TEXT NOT NULL, -- 'user' or 'claude'
    message TEXT NOT NULL,
    intent_detected TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (call_session_id) REFERENCES call_sessions(id)
);

-- 8. AGENT EXECUTIONS TABLE (tracks prompt refiner + dispatcher pipeline)
CREATE TABLE IF NOT EXISTS agent_executions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    stage TEXT NOT NULL,          -- 'refine', 'dispatch', 'execute', 'complete'
    agent_type TEXT NOT NULL,     -- 'prompt_refiner', 'dispatcher', 'local_agent'
    input_prompt TEXT,
    refined_prompt TEXT,
    output_result TEXT,
    explanation TEXT,
    status TEXT DEFAULT 'pending', -- 'pending', 'running', 'success', 'failed'
    error_message TEXT,
    execution_time_ms INTEGER,
    terminal_command_id TEXT,     -- link to terminal_commands when stage='terminal'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- Helpful indexes for dashboard queries
CREATE INDEX IF NOT EXISTS idx_projects_user_last_accessed ON projects(user_id, last_accessed);
CREATE INDEX IF NOT EXISTS idx_tasks_user_created_at ON tasks(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_project_created_at ON tasks(project_id, created_at);

-- Helpful indexes for terminal queries
CREATE INDEX IF NOT EXISTS idx_instances_project_heartbeat ON instances(project_id, last_heartbeat);
CREATE INDEX IF NOT EXISTS idx_agent_tokens_user_created ON agent_tokens(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_terminal_sessions_user_project ON terminal_sessions(user_id, project_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_terminal_commands_session_created ON terminal_commands(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_terminal_logs_command_sequence ON terminal_logs(command_id, sequence);
CREATE INDEX IF NOT EXISTS idx_conversation_turns_user_project_created ON conversation_turns(user_id, project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conversation_state_user_project ON conversation_state(user_id, project_id);
CREATE INDEX IF NOT EXISTS idx_companion_devices_user_created ON companion_devices(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_device_project_links_device_project ON device_project_links(device_id, project_id);
CREATE INDEX IF NOT EXISTS idx_cursor_context_device_project_created ON cursor_context_snapshots(device_id, project_id, created_at);