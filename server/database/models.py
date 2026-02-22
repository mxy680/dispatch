# server/database/models.py
from database.connection import get_db_connection
import uuid
from datetime import datetime

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
    return project_id

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

def create_task(project_id, description, voice_command=None):
    """Create a new task for a project."""
    conn = get_db_connection()
    task_id = str(uuid.uuid4())

    conn.execute(
        "INSERT INTO tasks (id, project_id, description, voice_command) VALUES (?, ?, ?, ?)",
        (task_id, project_id, description, voice_command)
    )
    conn.commit()
    conn.close()
    return task_id

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