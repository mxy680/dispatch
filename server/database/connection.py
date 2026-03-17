# server/database/connection.py
import sqlite3
import os
from pathlib import Path

# Saves dispatch.db in the 'server' folder
DB_PATH = Path(__file__).resolve().parent.parent / "dispatch.db"

def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}  # (cid, name, type, notnull, dflt_value, pk)

def _ensure_column(conn: sqlite3.Connection, table: str, col: str, col_def: str):
    cols = _table_columns(conn, table)
    if col in cols:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")

def _run_migrations(conn: sqlite3.Connection):
    # If tables don't exist yet, schema.sql will create them; migrations are for existing DBs.
    existing_tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }

    # Add missing columns for upgraded schema
    if "tasks" in existing_tables:
        _ensure_column(conn, "tasks", "user_id", "TEXT")
        _ensure_column(conn, "tasks", "voice_command", "TEXT")
        _ensure_column(conn, "tasks", "output_summary", "TEXT")
        _ensure_column(conn, "tasks", "intent_type", "TEXT")
        _ensure_column(conn, "tasks", "intent_confidence", "REAL")
        _ensure_column(conn, "tasks", "raw_transcript", "TEXT")
        _ensure_column(conn, "tasks", "terminal_session_id", "TEXT")

    if "projects" in existing_tables:
        _ensure_column(conn, "projects", "description", "TEXT")
        _ensure_column(conn, "projects", "file_path", "TEXT")
        _ensure_column(conn, "projects", "status", "TEXT DEFAULT 'active'")
        _ensure_column(conn, "projects", "last_accessed", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # agent_executions table (new)
    if "agent_executions" not in existing_tables:
        conn.execute("""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)
    else:
        _ensure_column(conn, "agent_executions", "terminal_command_id", "TEXT")

    # instances table upgrades (existing DBs)
    if "instances" in existing_tables:
        _ensure_column(conn, "instances", "user_id", "TEXT")
        _ensure_column(conn, "instances", "instance_token", "TEXT")
        _ensure_column(conn, "instances", "metadata", "TEXT")
        _ensure_column(conn, "instances", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # terminal tables (new)
    if "terminal_sessions" not in existing_tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS terminal_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                instance_id TEXT,
                name TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (instance_id) REFERENCES instances(id)
            )
        """)

    if "terminal_commands" not in existing_tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS terminal_commands (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                command TEXT NOT NULL,
                status TEXT DEFAULT 'queued',
                exit_code INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES terminal_sessions(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

    if "terminal_logs" not in existing_tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS terminal_logs (
                id TEXT PRIMARY KEY,
                command_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                stream TEXT NOT NULL,
                chunk TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (command_id) REFERENCES terminal_commands(id)
            )
        """)

    # Indexes (idempotent) - keep here so they run AFTER columns exist
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_user_last_accessed ON projects(user_id, last_accessed)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_created_at ON tasks(user_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project_created_at ON tasks(project_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_instances_project_heartbeat ON instances(project_id, last_heartbeat)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_terminal_sessions_user_project ON terminal_sessions(user_id, project_id, updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_terminal_commands_session_created ON terminal_commands(session_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_terminal_logs_command_sequence ON terminal_logs(command_id, sequence)")

def init_database():
    conn = get_db_connection()
    schema_path = Path(__file__).parent / "schema.sql"

    # 1) Create missing tables, but DO NOT run index statements yet (they may reference missing columns)
    with open(schema_path, "r") as f:
        raw_sql = f.read()

    # naive but effective: drop CREATE INDEX statements from the first pass
    lines = raw_sql.splitlines()
    filtered = []
    for line in lines:
        if line.lstrip().upper().startswith("CREATE INDEX"):
            continue
        filtered.append(line)
    conn.executescript("\n".join(filtered))

    # 2) Migrate existing tables to newer schema (adds missing columns)
    _run_migrations(conn)

    conn.commit()
    conn.close()
    print(f"✅ SQLite Database initialized/migrated at {DB_PATH}")

if __name__ == "__main__":
    init_database()