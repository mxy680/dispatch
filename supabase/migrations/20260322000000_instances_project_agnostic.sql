-- Make project_id optional on instances so an agent can run without a project context
ALTER TABLE instances ALTER COLUMN project_id DROP NOT NULL;

-- Remove the old project-scoped heartbeat index
DROP INDEX IF EXISTS idx_instances_project_heartbeat;

-- Add user-scoped heartbeat index (replaces project-scoped lookup)
CREATE INDEX IF NOT EXISTS idx_instances_user_heartbeat ON instances(user_id, last_heartbeat);

-- Unique constraint: one token per user (project-agnostic)
CREATE UNIQUE INDEX IF NOT EXISTS idx_instances_user_token
    ON instances(user_id, instance_token)
    WHERE instance_token IS NOT NULL;
