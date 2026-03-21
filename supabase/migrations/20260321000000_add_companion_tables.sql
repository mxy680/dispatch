-- Add companion device tables and terminal_commands extra columns

-- Companion devices (desktop companion registrations)
CREATE TABLE IF NOT EXISTS companion_devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    name TEXT,
    platform TEXT,
    status TEXT DEFAULT 'pending',
    pairing_code TEXT,
    pairing_expires_at TIMESTAMP WITH TIME ZONE,
    device_token_hash TEXT,
    last_heartbeat TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Device -> project links
CREATE TABLE IF NOT EXISTS device_project_links (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES companion_devices(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    local_path TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Cursor context snapshots (from local extension)
CREATE TABLE IF NOT EXISTS cursor_context_snapshots (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES companion_devices(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    file_path TEXT,
    selection TEXT,
    diagnostics TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Extra columns on terminal_commands for unified command center
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'terminal_commands' AND column_name = 'source') THEN
        ALTER TABLE terminal_commands ADD COLUMN source TEXT DEFAULT 'typed';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'terminal_commands' AND column_name = 'provider') THEN
        ALTER TABLE terminal_commands ADD COLUMN provider TEXT DEFAULT 'shell';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'terminal_commands' AND column_name = 'user_prompt') THEN
        ALTER TABLE terminal_commands ADD COLUMN user_prompt TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'terminal_commands' AND column_name = 'normalized_command') THEN
        ALTER TABLE terminal_commands ADD COLUMN normalized_command TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'terminal_commands' AND column_name = 'user_id') THEN
        ALTER TABLE terminal_commands ADD COLUMN user_id TEXT REFERENCES users(id);
    END IF;
END $$;

-- Extra column on agent_executions for terminal command link
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agent_executions' AND column_name = 'terminal_command_id') THEN
        ALTER TABLE agent_executions ADD COLUMN terminal_command_id TEXT REFERENCES terminal_commands(id);
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_companion_devices_user_created ON companion_devices(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_device_project_links_device_project ON device_project_links(device_id, project_id);
CREATE INDEX IF NOT EXISTS idx_cursor_context_device_project_created ON cursor_context_snapshots(device_id, project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_terminal_commands_user_id ON terminal_commands(user_id);
