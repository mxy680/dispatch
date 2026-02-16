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

-- 3. TASKS TABLE (Updated: "The Memory")
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    
    -- "The Brain" Context
    voice_command TEXT,      -- What the user actually said (SRS FR-5.2)
    description TEXT NOT NULL, -- The parsed intent/description
    
    -- "The Hands" Result
    output_summary TEXT,     -- What Claude actually did (SRS FR-5.2)
    
    status TEXT DEFAULT 'pending', -- 'pending', 'in_progress', 'completed', 'failed'
    assigned_to_claude_instance TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- 4. INSTANCES TABLE (New: Required for SRS FR-2.1 Orchestration)
CREATE TABLE IF NOT EXISTS instances (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    pid INTEGER,             -- Process ID on local machine
    status TEXT DEFAULT 'starting', -- 'running', 'stopped', 'error'
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id)
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
    voice_speed TEXT DEFAULT 'normal',
    email_notifications INTEGER DEFAULT 1,
    sms_notifications INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);