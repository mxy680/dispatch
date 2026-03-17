from __future__ import annotations

# server/database/models.py
from database.connection import get_db_connection
import uuid
import json
from datetime import datetime
import hashlib
import secrets

# ==================== USERS ====================
def upsert_user(user_id: str, email: str, phone_number: str | None = None):
    conn = get_db_connection()
    try:
        # Prefer stable upsert by primary key
        conn.execute(
            """
            INSERT INTO users (id, email, phone_number)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                email = COALESCE(excluded.email, users.email),
                phone_number = COALESCE(excluded.phone_number, users.phone_number)
            """,
            (user_id, email, phone_number),
        )
    except Exception:
        # Fallback: if email uniqueness causes issues (e.g., placeholder collisions),
        # ensure we at least have a row for this (id,email) pair.
        conn.execute(
            """
            INSERT INTO users (id, email, phone_number)
            VALUES (?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                id = excluded.id,
                phone_number = COALESCE(excluded.phone_number, users.phone_number)
            """,
            (user_id, email, phone_number),
        )
    conn.commit()
    conn.close()
    print(f"[DB] upsert_user user_id={user_id} email={email!r} phone={phone_number!r}")

# ==================== PROJECTS ====================

def create_project(user_id, name, file_path=None):
    """Create a new project for a user."""
    conn = get_db_connection()
    project_id = str(uuid.uuid4())
    
    conn.execute(
        "INSERT INTO projects (id, user_id, name, file_path) VALUES (?, ?, ?, ?)",
        (project_id, user_id, name, file_path)
    )
    conn.commit()
    conn.close()
    print(f"[DB] create_project id={project_id} user_id={user_id} name={name!r}")
    return project_id

def touch_project(project_id: str):
    conn = get_db_connection()
    conn.execute(
        "UPDATE projects SET last_accessed = CURRENT_TIMESTAMP WHERE id = ?",
        (project_id,),
    )
    conn.commit()
    conn.close()
    print(f"[DB] touch_project project_id={project_id}")

def get_user_projects(user_id):
    """Get all projects for a user."""
    conn = get_db_connection()
    projects = conn.execute(
        "SELECT * FROM projects WHERE user_id = ? ORDER BY last_accessed DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in projects]

def get_project_by_id(project_id):
    """Get a specific project by ID."""
    conn = get_db_connection()
    project = conn.execute(
        "SELECT * FROM projects WHERE id = ?",
        (project_id,)
    ).fetchone()
    conn.close()
    return dict(project) if project else None

def get_project_by_name(user_id, name):
    """Find a project by name (case-insensitive) for a specific user."""
    conn = get_db_connection()
    project = conn.execute(
        "SELECT * FROM projects WHERE user_id = ? AND LOWER(name) = LOWER(?)",
        (user_id, name)
    ).fetchone()
    conn.close()
    return dict(project) if project else None


def upsert_project_by_name(*, user_id: str, name: str, file_path: str | None = None) -> dict:
    """
    Find project by (user_id, name) and update file_path if provided; otherwise create it.
    """
    existing = get_project_by_name(user_id, name)
    if existing:
        if file_path and (existing.get("file_path") != file_path):
            conn = get_db_connection()
            conn.execute(
                "UPDATE projects SET file_path = ?, last_accessed = CURRENT_TIMESTAMP WHERE id = ?",
                (file_path, existing["id"]),
            )
            conn.commit()
            conn.close()
            existing["file_path"] = file_path
        return existing

    project_id = create_project(user_id, name, file_path=file_path)
    p = get_project_by_id(project_id)
    return p or {"id": project_id, "user_id": user_id, "name": name, "file_path": file_path}

def get_user_projects_with_task_counts(user_id):
    """Get all projects for a user with counts of tasks by status."""
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT
            p.id, p.name, p.status,
            COUNT(t.id) as total_tasks,
            SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) as pending_tasks,
            SUM(CASE WHEN t.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress_tasks,
            SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) as completed_tasks
        FROM projects p
        LEFT JOIN tasks t ON p.id = t.project_id
        WHERE p.user_id = ?
        GROUP BY p.id
        ORDER BY p.last_accessed DESC
        """,
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ==================== TASKS ====================

def create_task(
    project_id,
    user_id,
    description,
    voice_command=None,
    raw_transcript=None,
    intent_type=None,
    intent_confidence=None,
    output_summary=None,
):
    conn = get_db_connection()
    task_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO tasks (
            id, project_id, user_id,
            description, voice_command,
            raw_transcript, intent_type, intent_confidence,
            output_summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id, project_id, user_id,
            description, voice_command,
            raw_transcript, intent_type, intent_confidence,
            output_summary,
        ),
    )
    conn.commit()
    conn.close()
    print(
        "[DB] create_task "
        f"id={task_id} user_id={user_id} project_id={project_id} "
        f"intent_type={intent_type!r} desc={description!r}"
    )
    return task_id

def log_agent_event_task(
    user_id: str,
    project_name: str | None,
    projects: list,
    description: str,
    raw_transcript: str,
    intent_type: str,
    intent_confidence,
    output_summary: str | None,
    voice_command: str | None = None,
):
    project_id = None
    if project_name:
        p = next((p for p in projects if (p.get("name", "").lower() == project_name.lower())), None)
        if p:
            project_id = p.get("id")

    if not project_id:
        project_id = create_project(user_id, "General")
        print(f"[DB] log_agent_event_task fallback_project='General' project_id={project_id} user_id={user_id}")
    else:
        print(f"[DB] log_agent_event_task resolved_project_id={project_id} user_id={user_id} project_name={project_name!r}")

    touch_project(project_id)
    tid = create_task(
        project_id=project_id,
        user_id=user_id,
        description=description,
        voice_command=voice_command,
        raw_transcript=raw_transcript,
        intent_type=intent_type,
        intent_confidence=intent_confidence,
        output_summary=output_summary,
    )
    print(f"[DB] log_agent_event_task wrote task_id={tid}")
    return tid

def get_user_tasks(user_id: str):
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT t.*, p.name as project_name
        FROM tasks t
        LEFT JOIN projects p ON p.id = t.project_id
        WHERE t.user_id = ?
        ORDER BY t.created_at DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    result = [dict(r) for r in rows]
    print(f"[DB] get_user_tasks user_id={user_id} count={len(result)}")
    return result

def get_project_tasks(project_id):
    """Get all tasks for a project."""
    conn = get_db_connection()
    tasks = conn.execute(
        "SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in tasks]

def update_task_status(task_id, status):
    """Update a task's status (pending, in_progress, completed)."""
    conn = get_db_connection()
    completed_at = datetime.now() if status == "completed" else None
    
    conn.execute(
        "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
        (status, completed_at, task_id)
    )
    conn.commit()
    conn.close()


def get_task_by_id(task_id: str) -> dict | None:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_task_terminal_session(task_id: str, terminal_session_id: str | None) -> None:
    conn = get_db_connection()
    conn.execute(
        "UPDATE tasks SET terminal_session_id = ? WHERE id = ?",
        (terminal_session_id, task_id),
    )
    conn.commit()
    conn.close()

# ==================== CALL SESSIONS ====================

def create_call_session(user_id, phone_number):
    """Create a new call session."""
    conn = get_db_connection()
    session_id = str(uuid.uuid4())
    
    conn.execute(
        "INSERT INTO call_sessions (id, user_id, phone_number) VALUES (?, ?, ?)",
        (session_id, user_id, phone_number)
    )
    conn.commit()
    conn.close()
    return session_id

def update_call_session(session_id, transcript, commands_executed):
    """Update call session with transcript and commands."""
    conn = get_db_connection()
    
    conn.execute(
        "UPDATE call_sessions SET transcript = ?, commands_executed = ?, ended_at = ? WHERE id = ?",
        (transcript, commands_executed, datetime.now(), session_id)
    )
    conn.commit()
    conn.close()

def get_user_call_history(user_id, limit=10):
    """Get recent call sessions for a user."""
    conn = get_db_connection()
    sessions = conn.execute(
        "SELECT * FROM call_sessions WHERE user_id = ? ORDER BY started_at DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    conn.close()
    return [dict(row) for row in sessions]

# ==================== AGENT EXECUTIONS ====================

def create_agent_execution(
    task_id: str,
    stage: str,
    agent_type: str,
    input_prompt: str = None,
    refined_prompt: str = None,
    status: str = "pending",
) -> str:
    conn = get_db_connection()
    exec_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO agent_executions
            (id, task_id, stage, agent_type, input_prompt, refined_prompt, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (exec_id, task_id, stage, agent_type, input_prompt, refined_prompt, status),
    )
    conn.commit()
    conn.close()
    print(f"[DB] create_agent_execution id={exec_id} task_id={task_id} stage={stage}")
    return exec_id


def update_agent_execution(
    exec_id: str,
    status: str,
    output_result: str = None,
    explanation: str = None,
    error_message: str = None,
    execution_time_ms: int = None,
    terminal_command_id: str | None = None,
):
    conn = get_db_connection()
    completed_at = datetime.now().isoformat() if status in ("success", "failed") else None
    conn.execute(
        """
        UPDATE agent_executions
        SET status = ?, output_result = ?, explanation = ?,
            error_message = ?, execution_time_ms = ?, completed_at = ?,
            terminal_command_id = COALESCE(?, terminal_command_id)
        WHERE id = ?
        """,
        (status, output_result, explanation, error_message, execution_time_ms, completed_at, terminal_command_id, exec_id),
    )
    conn.commit()
    conn.close()
    print(f"[DB] update_agent_execution id={exec_id} status={status}")


def store_agent_feedback(
    task_id: str,
    output: str,
    explanation: str,
    status: str,
):
    """Called by file_watcher when a result JSON is picked up."""
    exec_id = str(uuid.uuid4())
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO agent_executions
            (id, task_id, stage, agent_type, output_result, explanation, status, completed_at)
        VALUES (?, ?, 'complete', 'copilot_agent', ?, ?, ?, ?)
        """,
        (exec_id, task_id, output, explanation, status, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    print(f"[DB] store_agent_feedback task_id={task_id} status={status}")


def get_agent_executions(task_id: str) -> list:
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM agent_executions WHERE task_id = ? ORDER BY created_at ASC",
        (task_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_task_agent_status(task_id: str) -> dict:
    """Get latest agent execution status for a task."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM agent_executions WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else {"status": "none", "stage": "none"}


def get_user_agent_executions(user_id: str, limit: int = 20) -> list:
    """Get all agent executions for a user's tasks."""
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT ae.*, t.description as task_description, p.name as project_name
        FROM agent_executions ae
        JOIN tasks t ON t.id = ae.task_id
        LEFT JOIN projects p ON p.id = t.project_id
        WHERE t.user_id = ?
        ORDER BY ae.created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== INSTANCES (Local Agent Daemons) ====================

def register_instance(
    *,
    user_id: str,
    project_id: str,
    instance_token: str | None = None,
    pid: int | None = None,
    status: str = "starting",
    metadata: dict | None = None,
) -> dict:
    """
    Create or update a local agent instance record.
    Uses (project_id, instance_token) as a stable identity when provided.
    """
    conn = get_db_connection()
    try:
        existing = None
        if instance_token:
            existing = conn.execute(
                "SELECT * FROM instances WHERE project_id = ? AND instance_token = ? LIMIT 1",
                (project_id, instance_token),
            ).fetchone()

        if existing:
            instance_id = existing["id"]
            conn.execute(
                """
                UPDATE instances
                SET user_id = ?, pid = COALESCE(?, pid),
                    status = ?, metadata = ?, last_heartbeat = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (user_id, pid, status, json.dumps(metadata or {}), instance_id),
            )
        else:
            instance_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO instances (id, user_id, project_id, pid, instance_token, metadata, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (instance_id, user_id, project_id, pid, instance_token, json.dumps(metadata or {}), status),
            )

        conn.commit()
        row = conn.execute("SELECT * FROM instances WHERE id = ?", (instance_id,)).fetchone()
        return dict(row) if row else {"id": instance_id}
    finally:
        conn.close()


def update_instance_heartbeat(*, instance_id: str, status: str = "online") -> None:
    conn = get_db_connection()
    conn.execute(
        "UPDATE instances SET status = ?, last_heartbeat = CURRENT_TIMESTAMP WHERE id = ?",
        (status, instance_id),
    )
    conn.commit()
    conn.close()


def get_active_instances_for_project(project_id: str, within_seconds: int = 60) -> list[dict]:
    """
    Consider instances active if they've heartbeated recently.
    SQLite datetime comparison uses 'now' and seconds offsets.
    """
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM instances
        WHERE project_id = ?
          AND last_heartbeat >= datetime('now', ?)
        ORDER BY last_heartbeat DESC
        """,
        (project_id, f"-{within_seconds} seconds"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== TERMINAL SESSIONS / COMMANDS / LOGS ====================

def create_terminal_session(
    *,
    user_id: str,
    project_id: str,
    name: str | None = None,
    instance_id: str | None = None,
    status: str = "pending",
) -> str:
    conn = get_db_connection()
    session_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO terminal_sessions (id, user_id, project_id, instance_id, name, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, user_id, project_id, instance_id, name, status),
    )
    conn.commit()
    conn.close()
    return session_id


def touch_terminal_session(session_id: str) -> None:
    conn = get_db_connection()
    conn.execute(
        "UPDATE terminal_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (session_id,),
    )
    conn.commit()
    conn.close()


def set_terminal_session_status(session_id: str, status: str, closed: bool = False) -> None:
    conn = get_db_connection()
    if closed:
        conn.execute(
            """
            UPDATE terminal_sessions
            SET status = ?, updated_at = CURRENT_TIMESTAMP, closed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, session_id),
        )
    else:
        conn.execute(
            "UPDATE terminal_sessions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, session_id),
        )
    conn.commit()
    conn.close()


def bind_terminal_session_instance(session_id: str, instance_id: str | None) -> None:
    conn = get_db_connection()
    conn.execute(
        "UPDATE terminal_sessions SET instance_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (instance_id, session_id),
    )
    conn.commit()
    conn.close()


def get_terminal_session(session_id: str) -> dict | None:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM terminal_sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_terminal_sessions_for_project(*, user_id: str, project_id: str) -> list[dict]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM terminal_sessions
        WHERE user_id = ? AND project_id = ?
        ORDER BY updated_at DESC, created_at DESC
        """,
        (user_id, project_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_terminal_command(*, session_id: str, user_id: str, command: str) -> str:
    conn = get_db_connection()
    command_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO terminal_commands (id, session_id, user_id, command, status)
        VALUES (?, ?, ?, ?, 'queued')
        """,
        (command_id, session_id, user_id, command),
    )
    conn.execute(
        "UPDATE terminal_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (session_id,),
    )
    conn.commit()
    conn.close()
    return command_id


def list_terminal_commands_for_session(*, user_id: str, session_id: str, limit: int = 100) -> list[dict]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM terminal_commands
        WHERE user_id = ? AND session_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, session_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_terminal_command(command_id: str) -> dict | None:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM terminal_commands WHERE id = ?", (command_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def claim_next_queued_command_for_instance(*, instance_id: str) -> dict | None:
    """
    Local agent helper uses this to claim work.
    Concurrency note: SQLite doesn't have SELECT FOR UPDATE; we use an UPDATE guard on status.
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT tc.*
            FROM terminal_commands tc
            JOIN terminal_sessions ts ON ts.id = tc.session_id
            WHERE ts.instance_id = ?
              AND tc.status = 'queued'
            ORDER BY tc.created_at ASC
            LIMIT 1
            """,
            (instance_id,),
        ).fetchone()
        if not row:
            return None

        command_id = row["id"]
        res = conn.execute(
            """
            UPDATE terminal_commands
            SET status = 'running', started_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'queued'
            """,
            (command_id,),
        )
        if res.rowcount != 1:
            conn.commit()
            return None
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def complete_terminal_command(
    *,
    command_id: str,
    status: str,
    exit_code: int | None = None,
) -> None:
    conn = get_db_connection()
    conn.execute(
        """
        UPDATE terminal_commands
        SET status = ?, exit_code = ?, completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, exit_code, command_id),
    )
    conn.commit()
    conn.close()


def append_terminal_log_chunk(
    *,
    command_id: str,
    sequence: int,
    stream: str,
    chunk: str,
) -> None:
    conn = get_db_connection()
    log_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO terminal_logs (id, command_id, sequence, stream, chunk)
        VALUES (?, ?, ?, ?, ?)
        """,
        (log_id, command_id, sequence, stream, chunk),
    )
    conn.commit()
    conn.close()


def get_terminal_logs_for_command(
    *,
    command_id: str,
    after_sequence: int | None = None,
    limit: int = 200,
) -> list[dict]:
    conn = get_db_connection()
    if after_sequence is None:
        rows = conn.execute(
            """
            SELECT *
            FROM terminal_logs
            WHERE command_id = ?
            ORDER BY sequence ASC
            LIMIT ?
            """,
            (command_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM terminal_logs
            WHERE command_id = ? AND sequence > ?
            ORDER BY sequence ASC
            LIMIT ?
            """,
            (command_id, after_sequence, limit),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== AGENT TOKENS (Local Agent Pairing) ====================

def _hash_agent_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_agent_token(*, user_id: str, label: str | None = None) -> dict:
    """
    Returns a dict with:
      - token_id
      - token (PLAINTEXT; only returned once)
    """
    conn = get_db_connection()
    token_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    token_hash = _hash_agent_token(token)
    conn.execute(
        """
        INSERT INTO agent_tokens (id, user_id, label, token_hash)
        VALUES (?, ?, ?, ?)
        """,
        (token_id, user_id, label, token_hash),
    )
    conn.commit()
    conn.close()
    return {"token_id": token_id, "token": token, "label": label}


def list_agent_tokens(*, user_id: str) -> list[dict]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT id, user_id, label, created_at, last_used_at, revoked_at
        FROM agent_tokens
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def revoke_agent_token(*, user_id: str, token_id: str) -> None:
    conn = get_db_connection()
    conn.execute(
        """
        UPDATE agent_tokens
        SET revoked_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (token_id, user_id),
    )
    conn.commit()
    conn.close()


def get_user_id_for_agent_token(token: str) -> str | None:
    token_hash = _hash_agent_token(token)
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT id, user_id
        FROM agent_tokens
        WHERE token_hash = ?
          AND revoked_at IS NULL
        LIMIT 1
        """,
        (token_hash,),
    ).fetchone()
    if not row:
        conn.close()
        return None
    token_id = row["id"]
    user_id = row["user_id"]
    conn.execute(
        "UPDATE agent_tokens SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
        (token_id,),
    )
    conn.commit()
    conn.close()
    return user_id


# ==================== USER DATA DELETION ====================

def delete_user_history(user_id: str) -> dict:
    """
    Deletes user-owned activity data (not the Supabase account).
    Returns counts for confirmation UI.
    """
    conn = get_db_connection()
    try:
        counts = {}
        # terminal_logs via join to commands
        counts["terminal_logs"] = conn.execute(
            """
            SELECT COUNT(*)
            FROM terminal_logs tl
            JOIN terminal_commands tc ON tc.id = tl.command_id
            WHERE tc.user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
        conn.execute(
            """
            DELETE FROM terminal_logs
            WHERE command_id IN (SELECT id FROM terminal_commands WHERE user_id = ?)
            """,
            (user_id,),
        )

        counts["terminal_commands"] = conn.execute(
            "SELECT COUNT(*) FROM terminal_commands WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
        conn.execute("DELETE FROM terminal_commands WHERE user_id = ?", (user_id,))

        counts["terminal_sessions"] = conn.execute(
            "SELECT COUNT(*) FROM terminal_sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
        conn.execute("DELETE FROM terminal_sessions WHERE user_id = ?", (user_id,))

        # agent_executions via tasks
        counts["agent_executions"] = conn.execute(
            """
            SELECT COUNT(*)
            FROM agent_executions ae
            JOIN tasks t ON t.id = ae.task_id
            WHERE t.user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
        conn.execute(
            """
            DELETE FROM agent_executions
            WHERE task_id IN (SELECT id FROM tasks WHERE user_id = ?)
            """,
            (user_id,),
        )

        counts["intents"] = conn.execute(
            """
            SELECT COUNT(*)
            FROM intents i
            JOIN tasks t ON t.id = i.task_id
            WHERE t.user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM intents WHERE task_id IN (SELECT id FROM tasks WHERE user_id = ?)",
            (user_id,),
        )

        counts["tasks"] = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
        conn.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))

        counts["call_messages_log"] = conn.execute(
            """
            SELECT COUNT(*)
            FROM call_messages_log cml
            JOIN call_sessions cs ON cs.id = cml.call_session_id
            WHERE cs.user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
        conn.execute(
            """
            DELETE FROM call_messages_log
            WHERE call_session_id IN (SELECT id FROM call_sessions WHERE user_id = ?)
            """,
            (user_id,),
        )

        counts["call_sessions"] = conn.execute(
            "SELECT COUNT(*) FROM call_sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
        conn.execute("DELETE FROM call_sessions WHERE user_id = ?", (user_id,))

        # instances (local agents) are history-like
        counts["instances"] = conn.execute(
            "SELECT COUNT(*) FROM instances WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
        conn.execute("DELETE FROM instances WHERE user_id = ?", (user_id,))

        conn.commit()
        return counts
    finally:
        conn.close()