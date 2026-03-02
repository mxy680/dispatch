from __future__ import annotations

# server/database/models.py
from database.connection import get_db_connection
import uuid
from datetime import datetime

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
):
    conn = get_db_connection()
    completed_at = datetime.now().isoformat() if status in ("success", "failed") else None
    conn.execute(
        """
        UPDATE agent_executions
        SET status = ?, output_result = ?, explanation = ?,
            error_message = ?, execution_time_ms = ?, completed_at = ?
        WHERE id = ?
        """,
        (status, output_result, explanation, error_message, execution_time_ms, completed_at, exec_id),
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