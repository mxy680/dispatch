-- Projects Table
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tasks Table
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    assigned_to_claude_instance TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Call Sessions Table
CREATE TABLE IF NOT EXISTS call_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    phone_number TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    transcript TEXT,
    commands_executed TEXT
);

-- User Preferences Table
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    phone_number TEXT,
    default_project TEXT,
    voice_speed TEXT DEFAULT 'normal',
    email_notifications INTEGER DEFAULT 1,
    sms_notifications INTEGER DEFAULT 0
);