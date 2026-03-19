-- Add terminal_access column to user_preferences table.
-- This persists the per-user terminal auto-execution setting across server restarts.
ALTER TABLE user_preferences
    ADD COLUMN IF NOT EXISTS terminal_access BOOLEAN DEFAULT false;
