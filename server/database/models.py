from __future__ import annotations

# server/database/models.py
from database.connection import get_db_connection
import uuid
import json
from datetime import datetime, timedelta
import hashlib
import secrets
import logging
import os
import re

logger = logging.getLogger("callstack.db")

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
    logger.debug("upsert_user user_id=%s", user_id)

# ==================== PROJECTS ====================

def create_project(user_id, name, file_path=None):
    """Create a new project for a user."""
    conn = get_db_connection()
    project_id = str(uuid.uuid4())

    if file_path is None:
        file_path = compute_default_project_file_path(get_project_base_path_for_user(user_id), name)
    
    conn.execute(
        "INSERT INTO projects (id, user_id, name, file_path) VALUES (?, ?, ?, ?)",
        (project_id, user_id, name, file_path)
    )
    conn.commit()
    conn.close()

    # Ensure companion devices can claim this project's local folder.
    if file_path:
        link_device_project_local_path_if_missing_for_user_devices(user_id=user_id, project_id=project_id, local_path=file_path)

    logger.debug("create_project id=%s user_id=%s", project_id, user_id)
    return project_id

def touch_project(project_id: str):
    conn = get_db_connection()
    conn.execute(
        "UPDATE projects SET last_accessed = CURRENT_TIMESTAMP WHERE id = ?",
        (project_id,),
    )
    conn.commit()
    conn.close()
    logger.debug("touch_project project_id=%s", project_id)

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
        # If caller provided file_path, use it.
        if file_path and (existing.get("file_path") != file_path):
            conn = get_db_connection()
            conn.execute(
                "UPDATE projects SET file_path = ?, last_accessed = CURRENT_TIMESTAMP WHERE id = ?",
                (file_path, existing["id"]),
            )
            conn.commit()
            conn.close()
            existing["file_path"] = file_path
        # If file_path still missing, try computing from user base path.
        if not existing.get("file_path"):
            computed = compute_default_project_file_path(get_project_base_path_for_user(user_id), name)
            if computed:
                conn = get_db_connection()
                conn.execute(
                    "UPDATE projects SET file_path = ?, last_accessed = CURRENT_TIMESTAMP WHERE id = ?",
                    (computed, existing["id"]),
                )
                conn.commit()
                conn.close()
                existing["file_path"] = computed

        # If we now have a file_path, ensure devices can claim it (but don't override non-empty local_path).
        if existing.get("file_path"):
            link_device_project_local_path_if_missing_for_user_devices(
                user_id=user_id,
                project_id=existing["id"],
                local_path=existing["file_path"],
            )
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


def _ensure_user_preferences_row(user_id: str) -> None:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)",
        (user_id,),
    )
    conn.commit()
    conn.close()


def get_user_preferences(user_id: str) -> dict:
    _ensure_user_preferences_row(user_id)
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM user_preferences WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else {"user_id": user_id}


def get_default_provider_for_user(user_id: str) -> str:
    prefs = get_user_preferences(user_id)
    provider = (prefs.get("default_provider") or "cursor").strip().lower()
    if provider not in {"cursor", "claude", "shell"}:
        return "cursor"
    return provider


def set_default_provider_for_user(user_id: str, provider: str) -> None:
    provider = (provider or "").strip().lower()
    if provider not in {"cursor", "claude", "shell"}:
        provider = "cursor"
    _ensure_user_preferences_row(user_id)
    conn = get_db_connection()
    conn.execute(
        "UPDATE user_preferences SET default_provider = ? WHERE user_id = ?",
        (provider, user_id),
    )
    conn.commit()
    conn.close()


def set_terminal_access_for_user(user_id: str, granted: bool) -> None:
    _ensure_user_preferences_row(user_id)
    conn = get_db_connection()
    conn.execute(
        "UPDATE user_preferences SET terminal_access_granted = ? WHERE user_id = ?",
        (1 if granted else 0, user_id),
    )
    conn.commit()
    conn.close()


def get_terminal_access_for_user(user_id: str) -> bool:
    prefs = get_user_preferences(user_id)
    return bool(prefs.get("terminal_access_granted"))

# ==================== PROJECT BASE PATH ====================

def get_project_base_path_for_user(user_id: str) -> str | None:
    prefs = get_user_preferences(user_id)
    base_path = prefs.get("project_base_path")
    if not base_path:
        return None
    base_path = str(base_path).strip()
    return base_path if base_path else None


def set_project_base_path_for_user(user_id: str, base_path: str | None) -> None:
    _ensure_user_preferences_row(user_id)
    base_path = (base_path or "").strip()
    conn = get_db_connection()
    if not base_path:
        conn.execute("UPDATE user_preferences SET project_base_path = NULL WHERE user_id = ?", (user_id,))
    else:
        # Store as-is; worker will create folders locally.
        conn.execute("UPDATE user_preferences SET project_base_path = ? WHERE user_id = ?", (base_path, user_id))
    conn.commit()
    conn.close()


def _safe_project_folder_name(name: str) -> str:
    # Convert a project name into a filesystem-friendly folder name.
    n = (name or "").strip()
    if not n:
        n = "Project"
    # Avoid path traversal and invalid separators.
    n = n.replace("\\", "-").replace("/", "-")
    n = re.sub(r"[^A-Za-z0-9._-]+", "-", n)
    n = n.strip("-") or "Project"
    return n


def compute_default_project_file_path(base_path: str | None, project_name: str) -> str | None:
    if not base_path:
        return None
    base_path = str(base_path).strip()
    if not base_path or not os.path.isabs(base_path):
        return None
    safe_name = _safe_project_folder_name(project_name)
    return os.path.join(base_path, safe_name)

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
    logger.debug("create_task id=%s user_id=%s project_id=%s", task_id, user_id, project_id)
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
        logger.debug("log_agent_event_task fallback project_id=%s user_id=%s", project_id, user_id)
    else:
        logger.debug("log_agent_event_task resolved project_id=%s user_id=%s", project_id, user_id)

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
    logger.debug("log_agent_event_task task_id=%s", tid)
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
    logger.debug("get_user_tasks user_id=%s count=%s", user_id, len(result))
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
    logger.debug("create_agent_execution id=%s task_id=%s stage=%s", exec_id, task_id, stage)
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
    logger.debug("update_agent_execution id=%s status=%s", exec_id, status)


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
        VALUES (?, ?, 'complete', 'dispatcher', ?, ?, ?, ?)
        """,
        (exec_id, task_id, output, explanation, status, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    logger.debug("store_agent_feedback task_id=%s status=%s", task_id, status)


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


def create_terminal_command(
    *,
    session_id: str,
    user_id: str,
    command: str,
    source: str = "typed",
    provider: str = "shell",
    user_prompt: str | None = None,
    normalized_command: str | None = None,
) -> str:
    conn = get_db_connection()
    command_id = str(uuid.uuid4())
    normalized = normalized_command or command
    conn.execute(
        """
        INSERT INTO terminal_commands
            (id, session_id, user_id, command, source, provider, user_prompt, normalized_command, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued')
        """,
        (
            command_id,
            session_id,
            user_id,
            command,
            source,
            provider,
            user_prompt,
            normalized,
        ),
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


def get_or_create_terminal_session_for_project(
    *,
    user_id: str,
    project_id: str,
    name: str = "Unified Session",
    within_seconds: int = 180,
) -> dict:
    active = get_active_instances_for_project(project_id, within_seconds=within_seconds)
    instance_id = active[0]["id"] if active else None

    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT *
        FROM terminal_sessions
        WHERE user_id = ? AND project_id = ? AND name = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (user_id, project_id, name),
    ).fetchone()
    conn.close()

    if row:
        session = dict(row)
        if not session.get("instance_id") and instance_id:
            bind_terminal_session_instance(session["id"], instance_id)
            refreshed = get_terminal_session(session["id"])
            return refreshed or session
        return session

    session_id = create_terminal_session(
        user_id=user_id,
        project_id=project_id,
        name=name,
        instance_id=instance_id,
        status="pending",
    )
    created = get_terminal_session(session_id)
    return created or {"id": session_id, "project_id": project_id, "user_id": user_id}


def list_recent_terminal_commands_for_user(
    *,
    user_id: str,
    limit: int = 100,
) -> list[dict]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT
            tc.*,
            ts.project_id,
            ts.name AS session_name,
            p.name AS project_name
        FROM terminal_commands tc
        JOIN terminal_sessions ts ON ts.id = tc.session_id
        LEFT JOIN projects p ON p.id = ts.project_id
        WHERE tc.user_id = ?
        ORDER BY tc.created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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


def claim_next_queued_command_for_device(*, device_id: str) -> dict | None:
    """
    Claim the oldest queued command where command session project is linked to device.
    Returns the command dict with project_id and local_path attached.
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT tc.*, ts.project_id, dpl.local_path AS project_local_path
            FROM terminal_commands tc
            JOIN terminal_sessions ts ON ts.id = tc.session_id
            JOIN device_project_links dpl ON dpl.project_id = ts.project_id
            WHERE dpl.device_id = ?
              AND tc.status = 'queued'
            ORDER BY tc.created_at ASC
            LIMIT 1
            """,
            (device_id,),
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


def _hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_device_pairing(*, user_id: str, name: str | None, platform: str | None, expires_minutes: int = 10) -> dict:
    conn = get_db_connection()
    device_id = str(uuid.uuid4())
    pairing_code = secrets.token_urlsafe(8)
    expires_at = (datetime.utcnow() + timedelta(minutes=expires_minutes)).isoformat()
    conn.execute(
        """
        INSERT INTO companion_devices
            (id, user_id, name, platform, status, pairing_code, pairing_expires_at)
        VALUES (?, ?, ?, ?, 'pending', ?, ?)
        """,
        (device_id, user_id, name, platform, pairing_code, expires_at),
    )
    conn.commit()
    conn.close()
    return {"device_id": device_id, "pairing_code": pairing_code, "expires_at": expires_at}


def complete_device_pairing(*, pairing_code: str, device_name: str | None = None, platform: str | None = None) -> dict | None:
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT *
        FROM companion_devices
        WHERE pairing_code = ?
          AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (pairing_code,),
    ).fetchone()
    if not row:
        conn.close()
        return None
    device = dict(row)
    expires_at = device.get("pairing_expires_at")
    if expires_at and datetime.fromisoformat(expires_at) < datetime.utcnow():
        conn.close()
        return None
    token = secrets.token_urlsafe(32)
    token_hash = _hash_device_token(token)
    conn.execute(
        """
        UPDATE companion_devices
        SET name = COALESCE(?, name),
            platform = COALESCE(?, platform),
            status = 'online',
            pairing_code = NULL,
            pairing_expires_at = NULL,
            device_token_hash = ?,
            last_heartbeat = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (device_name, platform, token_hash, device["id"]),
    )
    conn.commit()
    conn.close()
    return {"device_id": device["id"], "user_id": device["user_id"], "device_token": token}


def get_device_by_token(device_token: str) -> dict | None:
    token_hash = _hash_device_token(device_token)
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT *
        FROM companion_devices
        WHERE device_token_hash = ?
        LIMIT 1
        """,
        (token_hash,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def touch_device_heartbeat(device_id: str) -> None:
    conn = get_db_connection()
    conn.execute(
        "UPDATE companion_devices SET status = 'online', last_heartbeat = CURRENT_TIMESTAMP WHERE id = ?",
        (device_id,),
    )
    conn.commit()
    conn.close()


def list_devices_for_user(user_id: str) -> list[dict]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT id, user_id, name, platform, status, last_heartbeat, created_at
        FROM companion_devices
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def link_device_project(*, device_id: str, project_id: str, local_path: str | None = None) -> dict:
    conn = get_db_connection()
    existing = conn.execute(
        """
        SELECT *
        FROM device_project_links
        WHERE device_id = ? AND project_id = ?
        LIMIT 1
        """,
        (device_id, project_id),
    ).fetchone()
    if existing:
        row = dict(existing)
        if local_path and row.get("local_path") != local_path:
            conn.execute(
                "UPDATE device_project_links SET local_path = ? WHERE id = ?",
                (local_path, row["id"]),
            )
            conn.commit()
            row["local_path"] = local_path
        conn.close()
        return row
    link_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO device_project_links (id, device_id, project_id, local_path)
        VALUES (?, ?, ?, ?)
        """,
        (link_id, device_id, project_id, local_path),
    )
    conn.commit()
    conn.close()
    return {"id": link_id, "device_id": device_id, "project_id": project_id, "local_path": local_path}


def _link_device_project_local_path_if_missing(*, device_id: str, project_id: str, local_path: str) -> None:
    """
    Set device_project_links.local_path to `local_path` only when it's currently empty/missing.
    This avoids overwriting user-customized local paths.
    """
    conn = get_db_connection()
    existing = conn.execute(
        """
        SELECT id, local_path
        FROM device_project_links
        WHERE device_id = ? AND project_id = ?
        LIMIT 1
        """,
        (device_id, project_id),
    ).fetchone()

    if existing:
        row = dict(existing)
        if not row.get("local_path"):
            conn.execute(
                "UPDATE device_project_links SET local_path = ? WHERE id = ?",
                (local_path, row["id"]),
            )
            conn.commit()
        conn.close()
        return

    link_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO device_project_links (id, device_id, project_id, local_path)
        VALUES (?, ?, ?, ?)
        """,
        (link_id, device_id, project_id, local_path),
    )
    conn.commit()
    conn.close()


def link_device_project_local_path_if_missing_for_user_devices(*, user_id: str, project_id: str, local_path: str) -> None:
    devices = list_devices_for_user(user_id)
    for d in devices:
        _link_device_project_local_path_if_missing(
            device_id=d["id"],
            project_id=project_id,
            local_path=local_path,
        )


def get_device_project_links(device_id: str) -> list[dict]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT dpl.*, p.name AS project_name
        FROM device_project_links dpl
        LEFT JOIN projects p ON p.id = dpl.project_id
        WHERE dpl.device_id = ?
        ORDER BY dpl.created_at DESC
        """,
        (device_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_cursor_context(
    *,
    device_id: str,
    project_id: str,
    file_path: str | None,
    selection: str | None,
    diagnostics: str | None,
) -> str:
    conn = get_db_connection()
    context_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO cursor_context_snapshots (id, device_id, project_id, file_path, selection, diagnostics)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (context_id, device_id, project_id, file_path, selection, diagnostics),
    )
    conn.commit()
    conn.close()
    return context_id


def get_latest_cursor_context(*, device_id: str, project_id: str) -> dict | None:
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT *
        FROM cursor_context_snapshots
        WHERE device_id = ? AND project_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (device_id, project_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ==================== USER DATA DELETION ====================

def delete_user_history(user_id: str) -> dict:
    """
    Deletes user-owned activity data (not the Supabase account).
    Returns counts for confirmation UI.
    """
    conn = get_db_connection()
    try:
        counts = {}
        counts["projects"] = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
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

        counts["cursor_context_snapshots"] = conn.execute(
            """
            SELECT COUNT(*)
            FROM cursor_context_snapshots ccs
            JOIN companion_devices cd ON cd.id = ccs.device_id
            WHERE cd.user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
        conn.execute(
            """
            DELETE FROM cursor_context_snapshots
            WHERE device_id IN (SELECT id FROM companion_devices WHERE user_id = ?)
            """,
            (user_id,),
        )

        counts["device_project_links"] = conn.execute(
            """
            SELECT COUNT(*)
            FROM device_project_links dpl
            JOIN companion_devices cd ON cd.id = dpl.device_id
            WHERE cd.user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
        conn.execute(
            """
            DELETE FROM device_project_links
            WHERE device_id IN (SELECT id FROM companion_devices WHERE user_id = ?)
            """,
            (user_id,),
        )

        counts["companion_devices"] = conn.execute(
            "SELECT COUNT(*) FROM companion_devices WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
        conn.execute("DELETE FROM companion_devices WHERE user_id = ?", (user_id,))

        # Finally remove the user's projects. By this point, all dependent rows
        # (tasks, terminal_sessions/commands/logs, instances, and device/cursor context)
        # have already been deleted to satisfy foreign key constraints.
        conn.execute("DELETE FROM projects WHERE user_id = ?", (user_id,))

        conn.commit()
        return counts
    finally:
        conn.close()