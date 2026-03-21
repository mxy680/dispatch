-- Add missing columns to user_preferences
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_preferences' AND column_name = 'default_provider') THEN
        ALTER TABLE user_preferences ADD COLUMN default_provider TEXT DEFAULT 'claude';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_preferences' AND column_name = 'project_base_path') THEN
        ALTER TABLE user_preferences ADD COLUMN project_base_path TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_preferences' AND column_name = 'terminal_access_granted') THEN
        ALTER TABLE user_preferences ADD COLUMN terminal_access_granted BOOLEAN DEFAULT false;
    END IF;
END $$;
