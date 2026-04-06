from __future__ import annotations

# server/database/models.py
"""Database operations via Supabase PostgREST client."""
from database.supabase_client import get_sb
from database import sidecar_store as _sidecar
import uuid
import json
from datetime import datetime, timezone, timedelta
import hashlib
import secrets
import logging
import os
import re

logger = logging.getLogger("callstack.db")

def _normalize_conversation_state_row(row: dict | None) -> dict | None:
    if not row:
        return None
    if row.get("project_id") == "":
        return {**row, "project_id": None}
    return row


def _first_or_none(res) -> dict | None:
    """PostgREST returns 406 when .maybe_single() gets 0 rows (single-object Accept). Use limit(1) + this."""
    if res is None:
        return None
    data = getattr(res, "data", None)
    if data is None:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _execute_single(query) -> dict | None:
    """Execute a single-row query with maybe_single fallback to limit(1)."""
    try:
        return _first_or_none(query.maybe_single().execute())
    except Exception:
        try:
            return _first_or_none(query.limit(1).execute())
        except Exception:
            return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==================== USERS ====================

def upsert_user(user_id: str, email: str, phone_number: str | None = None, telegram_chat_id: str | None = None):
    sb = get_sb()
    # Check if user already exists — if so, just update.
    existing = _execute_single(sb.table("users").select("id").eq("id", user_id))
    if existing:
        update = {"email": email}
        if phone_number:
            update["phone_number"] = phone_number
        if telegram_chat_id:
            update["telegram_chat_id"] = str(telegram_chat_id)
        sb.table("users").update(update).eq("id", user_id).execute()
    else:
        data = {"id": user_id, "email": email}
        if phone_number:
            data["phone_number"] = phone_number
        if telegram_chat_id:
            data["telegram_chat_id"] = str(telegram_chat_id)
        sb.table("users").insert(data).execute()
    logger.debug("upsert_user user_id=%s email=%r phone=%r telegram=%r", user_id, email, phone_number, telegram_chat_id)

def get_user_id_by_telegram_chat_id(chat_id: str | int) -> str | None:
    """Look up a user by their telegram chat_id."""
    sb = get_sb()
    res = sb.table("users").select("id").eq("telegram_chat_id", str(chat_id)).limit(1).execute()
    data = _first_or_none(res)
    return data["id"] if data else None


def update_user_phone_number(user_id: str, phone_number: str) -> None:
    """Update the phone_number column for a user row.

    Raises ValueError if the phone number is already linked to another account.
    """
    sb = get_sb()
    try:
        sb.table("users").update({"phone_number": phone_number}).eq("id", user_id).execute()
        logger.debug("update_user_phone_number user_id=%s phone=%r", user_id, phone_number)
    except Exception as e:
        err_str = str(e).lower()
        if "unique" in err_str or "duplicate" in err_str or "23505" in err_str:
            raise ValueError("This phone number is already linked to another account")
        raise


def get_user_phone_number(user_id: str) -> str | None:
    """Return the phone_number for a user, or None if not set."""
    sb = get_sb()
    result = sb.table("users").select("phone_number").eq("id", user_id).limit(1).execute()
    row = _first_or_none(result)
    if row:
        return row.get("phone_number")
    return None


# ==================== PROJECTS ====================

def create_project(user_id, name, file_path=None):
    sb = get_sb()
    project_id = str(uuid.uuid4())
    if file_path is None:
        file_path = compute_default_project_file_path(get_project_base_path_for_user(user_id), name)

    sb.table("projects").insert({
        "id": project_id,
        "user_id": user_id,
        "name": name,
        "file_path": file_path,
    }).execute()

    # Ensure companion devices can claim this project's local folder.
    if file_path:
        link_device_project_local_path_if_missing_for_user_devices(user_id=user_id, project_id=project_id, local_path=file_path)

    logger.debug("create_project id=%s user_id=%s name=%r", project_id, user_id, name)
    return project_id


def touch_project(project_id: str):
    sb = get_sb()
    sb.table("projects").update({"last_accessed": _now_iso()}).eq("id", project_id).execute()
    logger.debug("touch_project project_id=%s", project_id)


def delete_project(project_id: str):
    """Delete a project and its related data (tasks, sessions, commands, logs)."""
    sb = get_sb()
    # Delete in dependency order.
    # Terminal logs → commands → sessions
    sessions_res = sb.table("terminal_sessions").select("id").eq("project_id", project_id).execute()
    session_ids = [s["id"] for s in (sessions_res.data or [])]
    # Conversation turns + state (must precede terminal_commands due to FK on command_id)
    try:
        sb.table("conversation_turns").delete().eq("project_id", project_id).execute()
    except Exception:
        pass
    try:
        sb.table("conversation_state").delete().eq("project_id", project_id).execute()
    except Exception:
        pass
    if session_ids:
        cmds_res = sb.table("terminal_commands").select("id").in_("session_id", session_ids).execute()
        cmd_ids = [c["id"] for c in (cmds_res.data or [])]
        if cmd_ids:
            # Also clean up any conversation_turns referencing these commands
            try:
                sb.table("conversation_turns").delete().in_("command_id", cmd_ids).execute()
            except Exception:
                pass
            sb.table("terminal_logs").delete().in_("command_id", cmd_ids).execute()
            sb.table("terminal_commands").delete().in_("id", cmd_ids).execute()
        sb.table("terminal_sessions").delete().in_("id", session_ids).execute()
    # Tasks + agent executions
    tasks_res = sb.table("tasks").select("id").eq("project_id", project_id).execute()
    task_ids = [t["id"] for t in (tasks_res.data or [])]
    if task_ids:
        sb.table("agent_executions").delete().in_("task_id", task_ids).execute()
    sb.table("tasks").delete().eq("project_id", project_id).execute()
    # Instances (local agent registrations)
    sb.table("instances").delete().eq("project_id", project_id).execute()
    # Device project links
    sb.table("device_project_links").delete().eq("project_id", project_id).execute()
    # Cursor context
    sb.table("cursor_context_snapshots").delete().eq("project_id", project_id).execute()
    # Project itself
    sb.table("projects").delete().eq("id", project_id).execute()
    logger.debug("delete_project project_id=%s", project_id)


def get_user_projects(user_id):
    sb = get_sb()
    res = sb.table("projects").select("*").eq("user_id", user_id).order("last_accessed", desc=True).execute()
    return res.data or []


def get_project_by_id(project_id):
    sb = get_sb()
    return _execute_single(sb.table("projects").select("*").eq("id", project_id))


def get_project_by_name(user_id, name):
    sb = get_sb()
    return _execute_single(sb.table("projects").select("*").eq("user_id", user_id).ilike("name", name))


def upsert_project_by_name(*, user_id: str, name: str, file_path: str | None = None) -> dict:
    existing = get_project_by_name(user_id, name)
    if existing:
        # If caller provided file_path, use it.
        if file_path and (existing.get("file_path") != file_path):
            sb = get_sb()
            sb.table("projects").update({
                "file_path": file_path,
                "last_accessed": _now_iso(),
            }).eq("id", existing["id"]).execute()
            existing["file_path"] = file_path
        # If file_path still missing, try computing from user base path.
        if not existing.get("file_path"):
            computed = compute_default_project_file_path(get_project_base_path_for_user(user_id), name)
            if computed:
                sb = get_sb()
                sb.table("projects").update({
                    "file_path": computed,
                    "last_accessed": _now_iso(),
                }).eq("id", existing["id"]).execute()
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
    sb = get_sb()
    res = sb.rpc("get_user_projects_with_task_counts", {"p_user_id": user_id}).execute()
    return res.data or []



def _ensure_user_preferences_row(user_id: str) -> None:
    sb = get_sb()
    try:
        sb.table("user_preferences").upsert(
            {"user_id": user_id},
            on_conflict="user_id",
        ).execute()
    except Exception as e:
        # Some call paths (e.g. mocked telegram new-user tests) may not have users row inserted.
        # Do not break app flows just for missing preference bootstrap.
        if "23503" in str(e) or "foreign key" in str(e).lower():
            logger.warning("skip user_preferences bootstrap; users row missing for user_id=%s", user_id)
            return
        raise


def get_user_preferences(user_id: str) -> dict:
    _ensure_user_preferences_row(user_id)
    sb = get_sb()
    row = _execute_single(sb.table("user_preferences").select("*").eq("user_id", user_id))
    return row or {"user_id": user_id}


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
    sb = get_sb()
    sb.table("user_preferences").update({"default_provider": provider}).eq("user_id", user_id).execute()


def set_terminal_access_for_user(user_id: str, granted: bool) -> None:
    _ensure_user_preferences_row(user_id)
    sb = get_sb()
    sb.table("user_preferences").update({"terminal_access_granted": granted}).eq("user_id", user_id).execute()


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
    sb = get_sb()
    sb.table("user_preferences").update({
        "project_base_path": base_path if base_path else None,
    }).eq("user_id", user_id).execute()


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
    sb = get_sb()
    task_id = str(uuid.uuid4())
    sb.table("tasks").insert({
        "id": task_id,
        "project_id": project_id,
        "user_id": user_id,
        "description": description,
        "voice_command": voice_command,
        "raw_transcript": raw_transcript,
        "intent_type": intent_type,
        "intent_confidence": intent_confidence,
        "output_summary": output_summary,
    }).execute()
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
    sb = get_sb()
    res = sb.table("tasks").select("*, projects(name)").eq("user_id", user_id).order("created_at", desc=True).execute()
    raw_rows = res.data or []
    # Flatten: {projects: {name: "foo"}} -> {project_name: "foo"} (immutable reconstruction)
    result = []
    for row in raw_rows:
        proj = row.get("projects")
        result.append({
            **{k: v for k, v in row.items() if k != "projects"},
            "project_name": proj.get("name") if proj else None,
        })
    logger.debug("get_user_tasks user_id=%s count=%s", user_id, len(result))
    return result


def get_project_tasks(project_id):
    sb = get_sb()
    res = sb.table("tasks").select("*").eq("project_id", project_id).order("created_at", desc=True).execute()
    return res.data or []


def update_task_status(task_id, status):
    sb = get_sb()
    data = {"status": status}
    if status == "completed":
        data["completed_at"] = _now_iso()
    sb.table("tasks").update(data).eq("id", task_id).execute()


def get_task_by_id(task_id: str) -> dict | None:
    sb = get_sb()
    res = sb.table("tasks").select("*").eq("id", task_id).limit(1).execute()
    return _first_or_none(res)


def set_task_terminal_session(task_id: str, terminal_session_id: str | None) -> None:
    sb = get_sb()
    sb.table("tasks").update({"terminal_session_id": terminal_session_id}).eq("id", task_id).execute()


# ==================== CALL SESSIONS ====================

def get_user_id_by_phone(phone_number: str) -> str | None:
    """Look up a user by their phone number."""
    sb = get_sb()
    res = sb.table("users").select("id").eq("phone_number", phone_number).limit(1).execute()
    data = _first_or_none(res)
    return data["id"] if data else None

def create_call_session(user_id, phone_number):
    sb = get_sb()
    session_id = str(uuid.uuid4())
    sb.table("call_sessions").insert({
        "id": session_id,
        "user_id": user_id,
        "phone_number": phone_number,
    }).execute()
    return session_id


def update_call_session(session_id, transcript, commands_executed):
    sb = get_sb()
    sb.table("call_sessions").update({
        "transcript": transcript,
        "commands_executed": commands_executed,
        "ended_at": _now_iso(),
    }).eq("id", session_id).execute()


def get_user_call_history(user_id, limit=10):
    sb = get_sb()
    res = sb.table("call_sessions").select("*").eq("user_id", user_id).order("started_at", desc=True).limit(limit).execute()
    return res.data or []


# ==================== AGENT EXECUTIONS ====================

def create_agent_execution(
    task_id: str,
    stage: str,
    agent_type: str,
    input_prompt: str = None,
    refined_prompt: str = None,
    status: str = "pending",
) -> str:
    sb = get_sb()
    exec_id = str(uuid.uuid4())
    sb.table("agent_executions").insert({
        "id": exec_id,
        "task_id": task_id,
        "stage": stage,
        "agent_type": agent_type,
        "input_prompt": input_prompt,
        "refined_prompt": refined_prompt,
        "status": status,
    }).execute()
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
    sb = get_sb()
    data = {
        "status": status,
        "output_result": output_result,
        "explanation": explanation,
        "error_message": error_message,
        "execution_time_ms": execution_time_ms,
    }
    if status in ("success", "failed"):
        data["completed_at"] = _now_iso()
    if terminal_command_id is not None:
        data["terminal_command_id"] = terminal_command_id
    sb.table("agent_executions").update(data).eq("id", exec_id).execute()
    logger.debug("update_agent_execution id=%s status=%s", exec_id, status)


def store_agent_feedback(
    task_id: str,
    output: str,
    explanation: str,
    status: str,
):
    sb = get_sb()
    exec_id = str(uuid.uuid4())
    sb.table("agent_executions").insert({
        "id": exec_id,
        "task_id": task_id,
        "stage": "complete",
        "agent_type": "copilot_agent",
        "output_result": output,
        "explanation": explanation,
        "status": status,
        "completed_at": _now_iso(),
    }).execute()
    logger.debug("store_agent_feedback task_id=%s status=%s", task_id, status)


def get_agent_executions(task_id: str) -> list:
    sb = get_sb()
    res = sb.table("agent_executions").select("*").eq("task_id", task_id).order("created_at").execute()
    return res.data or []


def get_task_agent_status(task_id: str) -> dict:
    sb = get_sb()
    res = sb.table("agent_executions").select("*").eq("task_id", task_id).order("created_at", desc=True).limit(1).execute()
    return _first_or_none(res) or {"status": "none", "stage": "none"}


def get_user_agent_executions(user_id: str, limit: int = 20) -> list:
    sb = get_sb()
    res = (
        sb.table("agent_executions")
        .select("*, tasks!inner(user_id, description, projects(name))")
        .eq("tasks.user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    raw_rows = res.data or []
    # Flatten nested task/project info (immutable reconstruction)
    result = []
    for row in raw_rows:
        task_info = row.get("tasks")
        if task_info:
            proj = task_info.get("projects")
            task_description = task_info.get("description")
            project_name = proj.get("name") if proj else None
        else:
            task_description = None
            project_name = None
        result.append({
            **{k: v for k, v in row.items() if k != "tasks"},
            "task_description": task_description,
            "project_name": project_name,
        })
    return result


# ==================== INSTANCES (Local Agent Daemons) ====================

def register_instance(
    *,
    user_id: str,
    project_id: str | None = None,
    instance_token: str | None = None,
    pid: int | None = None,
    status: str = "starting",
    metadata: dict | None = None,
) -> dict:
    sb = get_sb()
    existing = None
    if instance_token:
        existing = _execute_single(
            sb.table("instances").select("*").eq("user_id", user_id).eq("instance_token", instance_token)
        )

    if existing:
        instance_id = existing["id"]
        update_data = {
            "user_id": user_id,
            "status": status,
            "metadata": json.dumps(metadata or {}),
            "last_heartbeat": _now_iso(),
        }
        if pid is not None:
            update_data["pid"] = pid
        if project_id is not None:
            update_data["project_id"] = project_id
        sb.table("instances").update(update_data).eq("id", instance_id).execute()
    else:
        instance_id = str(uuid.uuid4())
        insert_data: dict = {
            "id": instance_id,
            "user_id": user_id,
            "pid": pid,
            "instance_token": instance_token,
            "metadata": json.dumps(metadata or {}),
            "status": status,
        }
        if project_id is not None:
            insert_data["project_id"] = project_id
        sb.table("instances").insert(insert_data).execute()

    row = _execute_single(sb.table("instances").select("*").eq("id", instance_id))
    return row or {"id": instance_id}


def get_instance_by_id(instance_id: str) -> dict | None:
    sb = get_sb()
    return _execute_single(sb.table("instances").select("*").eq("id", instance_id))


def update_instance_heartbeat(*, instance_id: str, status: str = "online") -> None:
    sb = get_sb()
    sb.table("instances").update({
        "status": status,
        "last_heartbeat": _now_iso(),
    }).eq("id", instance_id).execute()


def get_active_instances_for_project(project_id: str, within_seconds: int = 60) -> list[dict]:
    sb = get_sb()
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=within_seconds)).isoformat()
    res = (
        sb.table("instances")
        .select("*")
        .eq("project_id", project_id)
        .gte("last_heartbeat", cutoff)
        .order("last_heartbeat", desc=True)
        .execute()
    )
    return res.data or []


def get_active_instances_for_user(user_id: str, within_seconds: int = 60) -> list[dict]:
    sb = get_sb()
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=within_seconds)).isoformat()
    res = (
        sb.table("instances")
        .select("*")
        .eq("user_id", user_id)
        .gte("last_heartbeat", cutoff)
        .order("last_heartbeat", desc=True)
        .execute()
    )
    return res.data or []


# ==================== TERMINAL SESSIONS / COMMANDS / LOGS ====================

def create_terminal_session(
    *,
    user_id: str,
    project_id: str,
    name: str | None = None,
    instance_id: str | None = None,
    status: str = "pending",
) -> str:
    sb = get_sb()
    session_id = str(uuid.uuid4())
    sb.table("terminal_sessions").insert({
        "id": session_id,
        "user_id": user_id,
        "project_id": project_id,
        "instance_id": instance_id,
        "name": name,
        "status": status,
    }).execute()
    return session_id


def touch_terminal_session(session_id: str) -> None:
    sb = get_sb()
    sb.table("terminal_sessions").update({"updated_at": _now_iso()}).eq("id", session_id).execute()


def set_terminal_session_status(session_id: str, status: str, closed: bool = False) -> None:
    sb = get_sb()
    data = {"status": status, "updated_at": _now_iso()}
    if closed:
        data["closed_at"] = _now_iso()
    sb.table("terminal_sessions").update(data).eq("id", session_id).execute()


def bind_terminal_session_instance(session_id: str, instance_id: str | None) -> None:
    sb = get_sb()
    sb.table("terminal_sessions").update({
        "instance_id": instance_id,
        "updated_at": _now_iso(),
    }).eq("id", session_id).execute()


def get_terminal_session(session_id: str) -> dict | None:
    sb = get_sb()
    res = sb.table("terminal_sessions").select("*").eq("id", session_id).limit(1).execute()
    return _first_or_none(res)


def list_terminal_sessions_for_project(*, user_id: str, project_id: str) -> list[dict]:
    sb = get_sb()
    res = (
        sb.table("terminal_sessions")
        .select("*")
        .eq("user_id", user_id)
        .eq("project_id", project_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return res.data or []


def create_terminal_command(
    *,
    session_id: str,
    user_id: str,
    command: str,
    source: str = "typed",
    provider: str = "shell",
    user_prompt: str | None = None,
    normalized_command: str | None = None,
    status: str = "queued",
) -> str:
    sb = get_sb()
    command_id = str(uuid.uuid4())
    normalized = normalized_command or command
    sb.table("terminal_commands").insert({
        "id": command_id,
        "session_id": session_id,
        "user_id": user_id,
        "command": command,
        "source": source,
        "provider": provider,
        "user_prompt": user_prompt,
        "normalized_command": normalized,
        "status": status,
    }).execute()
    _sidecar.set_command_risk(
        command_id=command_id,
        user_id=user_id,
        risk_level="PENDING",
        risk_reason=None,
        plain_summary="I prepared this action and I am waiting for your approval before I run it.",
    )
    # Update session timestamp (non-transactional, cosmetic)
    sb.table("terminal_sessions").update({"updated_at": _now_iso()}).eq("id", session_id).execute()
    return command_id


def list_terminal_commands_for_session(*, user_id: str, session_id: str, limit: int = 100) -> list[dict]:
    sb = get_sb()
    res = (
        sb.table("terminal_commands")
        .select("*")
        .eq("user_id", user_id)
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return _sidecar.enrich_commands(res.data or [])


def get_terminal_command(command_id: str) -> dict | None:
    sb = get_sb()
    res = sb.table("terminal_commands").select("*").eq("id", command_id).limit(1).execute()
    return _sidecar.enrich_command(_first_or_none(res))


def get_or_create_terminal_session_for_project(
    *,
    user_id: str,
    project_id: str,
    name: str = "Unified Session",
    within_seconds: int = 180,
) -> dict:
    active = get_active_instances_for_user(user_id, within_seconds=within_seconds)
    instance_id = active[0]["id"] if active else None

    sb = get_sb()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_iso = cutoff.isoformat()
    res = (
        sb.table("terminal_sessions")
        .select("*")
        .eq("user_id", user_id)
        .eq("project_id", project_id)
        .eq("name", name)
        .gte("updated_at", cutoff_iso)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    session = _first_or_none(res)

    if session:
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
    sb = get_sb()
    res = (
        sb.table("terminal_commands")
        .select("*, terminal_sessions!inner(project_id, name, projects(name))")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    raw_rows = res.data or []
    # Flatten nested session/project info (immutable reconstruction)
    result = []
    for row in raw_rows:
        ts = row.get("terminal_sessions")
        project_id = ts.get("project_id") if ts else None
        session_name = ts.get("name") if ts else None
        proj = ts.get("projects") if ts else None
        project_name = proj.get("name") if proj else None
        result.append({
            **{k: v for k, v in row.items() if k != "terminal_sessions"},
            "project_id": project_id,
            "session_name": session_name,
            "project_name": project_name,
        })
    return _sidecar.enrich_commands(result)


def _expire_stale_running_commands(user_id: str, stale_minutes: int = 5) -> None:
    """Mark commands stuck in 'running' for too long as failed."""
    sb = get_sb()
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()
    stale_res = (
        sb.table("terminal_commands")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "running")
        .lt("started_at", cutoff)
        .execute()
    )
    for cmd in (stale_res.data or []):
        sb.table("terminal_commands").update({
            "status": "failed",
            "exit_code": -1,
            "completed_at": _now_iso(),
        }).eq("id", cmd["id"]).execute()
        logger.warning("expired stale running command id=%s user=%s", cmd["id"], user_id)


def _expire_stale_running_commands_for_sessions(session_ids: list[str], stale_minutes: int = 5) -> None:
    """Mark commands stuck in 'running' for too long as failed, filtered by session IDs."""
    if not session_ids:
        return
    sb = get_sb()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()
    stale_res = (
        sb.table("terminal_commands")
        .select("id")
        .in_("session_id", session_ids)
        .eq("status", "running")
        .lt("started_at", cutoff)
        .execute()
    )
    for cmd in (stale_res.data or []):
        sb.table("terminal_commands").update({
            "status": "failed",
            "exit_code": -1,
            "completed_at": _now_iso(),
        }).eq("id", cmd["id"]).execute()
        logger.warning("expired stale running command id=%s (device path)", cmd["id"])


def claim_next_queued_command_for_user(*, user_id: str) -> dict | None:
    """Claim the oldest queued command across ALL of the user's projects."""
    sb = get_sb()

    # Expire any commands stuck as "running" for too long.
    _expire_stale_running_commands(user_id)

    # Find the oldest queued command belonging to this user.
    cmd_res = (
        sb.table("terminal_commands")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "queued")
        .order("created_at")
        .limit(1)
    )
    cmd = _execute_single(cmd_res)
    if not cmd:
        return None

    # Claim it (update only if still queued).
    sb.table("terminal_commands").update({
        "status": "running",
        "started_at": _now_iso(),
    }).eq("id", cmd["id"]).eq("status", "queued").execute()

    # Re-fetch to confirm claim.
    verified = _execute_single(sb.table("terminal_commands").select("*").eq("id", cmd["id"]))
    if not verified or verified.get("status") != "running":
        return None

    # Attach project file_path so the agent knows where to run.
    session_id = verified.get("session_id")
    if session_id:
        sess_row = _execute_single(sb.table("terminal_sessions").select("project_id").eq("id", session_id))
        if sess_row:
            pid = sess_row.get("project_id")
            proj_row = _execute_single(sb.table("projects").select("file_path").eq("id", pid))
            if proj_row:
                verified["project_path"] = proj_row.get("file_path")

    return _sidecar.enrich_command(verified)


def claim_next_queued_command_for_instance(*, instance_id: str) -> dict | None:
    """Claim the oldest queued terminal command for a particular instance."""
    sb = get_sb()

    # Find all sessions assigned to this instance.
    sessions_res = (
        sb.table("terminal_sessions")
        .select("id, project_id, name")
        .eq("instance_id", instance_id)
        .execute()
    )
    sessions = sessions_res.data if sessions_res else []
    if not sessions:
        return None

    session_ids = [s["id"] for s in sessions]
    session_project_map = {s["id"]: s["project_id"] for s in sessions}

    cmd_res = (
        sb.table("terminal_commands")
        .select("*")
        .in_("session_id", session_ids)
        .eq("status", "queued")
        .order("created_at")
        .limit(1)
        .maybe_single()
        .execute()
    )
    cmd = cmd_res.data if cmd_res else None
    if not cmd:
        return None

    command_id = cmd["id"]
    sb.table("terminal_commands").update({
        "status": "running",
        "started_at": _now_iso(),
    }).eq("id", command_id).eq("status", "queued").execute()

    verify_res = sb.table("terminal_commands").select("*").eq("id", command_id).maybe_single().execute()
    verified = verify_res.data if verify_res else None
    if not verified or verified.get("status") != "running":
        return None

    return {
        **verified,
        "project_id": session_project_map.get(cmd["session_id"]),
    }


def complete_terminal_command(
    *,
    command_id: str,
    status: str,
    exit_code: int | None = None,
) -> None:
    sb = get_sb()
    sb.table("terminal_commands").update({
        "status": status,
        "exit_code": exit_code,
        "completed_at": _now_iso(),
    }).eq("id", command_id).execute()


def update_terminal_command_for_approval(
    *,
    command_id: str,
    status: str,
    command: str | None = None,
    normalized_command: str | None = None,
    reset_risk_pending: bool = False,
) -> dict | None:
    sb = get_sb()
    payload = {"status": status}
    if command is not None:
        payload["command"] = command
    if normalized_command is not None:
        payload["normalized_command"] = normalized_command
    sb.table("terminal_commands").update(payload).eq("id", command_id).execute()
    if reset_risk_pending:
        uid_row = _first_or_none(
            sb.table("terminal_commands").select("user_id").eq("id", command_id).limit(1).execute()
        )
        if uid_row:
            _sidecar.reset_command_risk_pending(command_id=command_id, user_id=uid_row["user_id"])
    res = sb.table("terminal_commands").select("*").eq("id", command_id).limit(1).execute()
    return _sidecar.enrich_command(_first_or_none(res))


def update_command_risk_assessment(
    *,
    command_id: str,
    risk_level: str,
    risk_reason: str | None,
    plain_summary: str | None = None,
    user_id: str | None = None,
) -> None:
    level = (risk_level or "PENDING").strip().upper()
    if level not in {"PENDING", "SAFE", "WARNING", "HIGH_RISK"}:
        level = "WARNING"
    uid = user_id
    if not uid:
        sb = get_sb()
        row = _first_or_none(
            sb.table("terminal_commands").select("user_id").eq("id", command_id).limit(1).execute()
        )
        uid = row["user_id"] if row else ""
    if not uid:
        logger.warning("update_command_risk_assessment: missing user_id for command_id=%s", command_id)
        return
    _sidecar.set_command_risk(
        command_id=command_id,
        user_id=uid,
        risk_level=level,
        risk_reason=risk_reason,
        plain_summary=plain_summary,
    )


def append_terminal_log_chunk(
    *,
    command_id: str,
    sequence: int,
    stream: str,
    chunk: str,
) -> None:
    sb = get_sb()
    log_id = str(uuid.uuid4())
    sb.table("terminal_logs").insert({
        "id": log_id,
        "command_id": command_id,
        "sequence": sequence,
        "stream": stream,
        "chunk": chunk,
    }).execute()


def get_terminal_logs_for_command(
    *,
    command_id: str,
    after_sequence: int | None = None,
    limit: int = 200,
) -> list[dict]:
    sb = get_sb()
    query = sb.table("terminal_logs").select("*").eq("command_id", command_id)
    if after_sequence is not None:
        query = query.gt("sequence", after_sequence)
    res = query.order("sequence").limit(limit).execute()
    return res.data or []


def add_conversation_turn(
    *,
    user_id: str,
    project_id: str | None,
    session_id: str | None,
    command_id: str | None,
    role: str,
    turn_type: str,
    content: str,
) -> dict:
    return _sidecar.add_conversation_turn(
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
        command_id=command_id,
        role=role,
        turn_type=turn_type,
        content=content,
    )


def list_conversation_turns_for_user(*, user_id: str, project_id: str | None = None, limit: int = 100) -> list[dict]:
    return _sidecar.list_conversation_turns_for_user(user_id=user_id, project_id=project_id, limit=limit)


def get_conversation_state(*, user_id: str, project_id: str | None) -> dict | None:
    return _normalize_conversation_state_row(
        _sidecar.get_conversation_state(user_id=user_id, project_id=project_id)
    )


def upsert_conversation_state(
    *,
    user_id: str,
    project_id: str | None,
    state: str,
    active_command_id: str | None,
    context_json: dict | None = None,
) -> dict:
    row = _sidecar.upsert_conversation_state(
        user_id=user_id,
        project_id=project_id,
        state=state,
        active_command_id=active_command_id,
        context_json=context_json,
    )
    return _normalize_conversation_state_row(row) or row


def claim_next_queued_command_for_device(*, device_id: str) -> dict | None:
    """
    Claim the oldest queued command where command session project is linked to device.
    Returns the command dict with project_id and local_path attached.
    Uses an RPC function for atomicity, falling back to a two-step approach.
    """
    sb = get_sb()
    # Step 1: Find the oldest queued command linked to this device.
    # Get project IDs linked to this device first.
    links_res = sb.table("device_project_links").select("project_id, local_path").eq("device_id", device_id).execute()
    links = links_res.data or []
    if not links:
        return None

    project_ids = [lnk["project_id"] for lnk in links]
    local_path_map = {lnk["project_id"]: lnk.get("local_path") for lnk in links}

    # Find sessions for those projects.
    sessions_res = sb.table("terminal_sessions").select("id, project_id").in_("project_id", project_ids).execute()
    sessions = sessions_res.data or []
    if not sessions:
        return None

    session_ids = [s["id"] for s in sessions]
    session_project_map = {s["id"]: s["project_id"] for s in sessions}

    # Expire any commands stuck as "running" for too long in these sessions.
    _expire_stale_running_commands_for_sessions(session_ids)

    # Find oldest queued command in those sessions.
    cmd_res = (
        sb.table("terminal_commands")
        .select("*")
        .in_("session_id", session_ids)
        .eq("status", "queued")
        .order("created_at")
        .limit(1)
        .execute()
    )
    cmd = _first_or_none(cmd_res)
    if not cmd:
        return None

    command_id = cmd["id"]

    # Step 2: Atomically claim it (update only if still queued).
    sb.table("terminal_commands").update({
        "status": "running",
        "started_at": _now_iso(),
    }).eq("id", command_id).eq("status", "queued").execute()

    # Re-fetch to confirm claim succeeded.
    verify_res = sb.table("terminal_commands").select("*").eq("id", command_id).limit(1).execute()
    verified = _first_or_none(verify_res)
    if not verified or verified.get("status") != "running":
        return None

    # Attach project_id and local_path.
    project_id = session_project_map.get(cmd["session_id"])
    return {
        **(_sidecar.enrich_command(verified) or verified),
        "project_id": project_id,
        "project_local_path": local_path_map.get(project_id),
    }


# ==================== AGENT TOKENS (Local Agent Pairing) ====================

def _hash_agent_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_agent_token(*, user_id: str, label: str | None = None) -> dict:
    sb = get_sb()
    token_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    token_hash = _hash_agent_token(token)
    sb.table("agent_tokens").insert({
        "id": token_id,
        "user_id": user_id,
        "label": label,
        "token_hash": token_hash,
    }).execute()
    return {"token_id": token_id, "token": token, "label": label}


def list_agent_tokens(*, user_id: str) -> list[dict]:
    sb = get_sb()
    res = (
        sb.table("agent_tokens")
        .select("id, user_id, label, created_at, last_used_at, revoked_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def revoke_agent_token(*, user_id: str, token_id: str) -> None:
    sb = get_sb()
    sb.table("agent_tokens").update({"revoked_at": _now_iso()}).eq("id", token_id).eq("user_id", user_id).execute()


def get_user_id_for_agent_token(token: str) -> str | None:
    sb = get_sb()
    token_hash = _hash_agent_token(token)
    res = (
        sb.table("agent_tokens")
        .select("id, user_id")
        .eq("token_hash", token_hash)
        .is_("revoked_at", "null")
        .limit(1)
        .execute()
    )
    data = _first_or_none(res)
    if not data:
        return None
    token_id = data["id"]
    user_id = data["user_id"]
    sb.table("agent_tokens").update({"last_used_at": _now_iso()}).eq("id", token_id).execute()
    return user_id


def _hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_device_pairing(*, user_id: str, name: str | None, platform: str | None, expires_minutes: int = 10) -> dict:
    sb = get_sb()
    device_id = str(uuid.uuid4())
    pairing_code = secrets.token_urlsafe(8)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)).isoformat()
    sb.table("companion_devices").insert({
        "id": device_id,
        "user_id": user_id,
        "name": name,
        "platform": platform,
        "status": "pending",
        "pairing_code": pairing_code,
        "pairing_expires_at": expires_at,
    }).execute()
    return {"device_id": device_id, "pairing_code": pairing_code, "expires_at": expires_at}


def complete_device_pairing(*, pairing_code: str, device_name: str | None = None, platform: str | None = None) -> dict | None:
    sb = get_sb()
    res = (
        sb.table("companion_devices")
        .select("*")
        .eq("pairing_code", pairing_code)
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    device = _first_or_none(res)
    if not device:
        return None
    expires_at = device.get("pairing_expires_at")
    if expires_at and datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
        return None
    token = secrets.token_urlsafe(32)
    token_hash = _hash_device_token(token)
    update_data = {
        "status": "online",
        "pairing_code": None,
        "pairing_expires_at": None,
        "device_token_hash": token_hash,
        "last_heartbeat": _now_iso(),
    }
    if device_name is not None:
        update_data["name"] = device_name
    if platform is not None:
        update_data["platform"] = platform
    sb.table("companion_devices").update(update_data).eq("id", device["id"]).execute()
    return {"device_id": device["id"], "user_id": device["user_id"], "device_token": token}


def get_device_by_token(device_token: str) -> dict | None:
    sb = get_sb()
    token_hash = _hash_device_token(device_token)
    res = sb.table("companion_devices").select("*").eq("device_token_hash", token_hash).limit(1).execute()
    return _first_or_none(res)


def touch_device_heartbeat(device_id: str) -> None:
    sb = get_sb()
    sb.table("companion_devices").update({
        "status": "online",
        "last_heartbeat": _now_iso(),
    }).eq("id", device_id).execute()


def list_devices_for_user(user_id: str) -> list[dict]:
    sb = get_sb()
    res = (
        sb.table("companion_devices")
        .select("id, user_id, name, platform, status, last_heartbeat, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def link_device_project(*, device_id: str, project_id: str, local_path: str | None = None) -> dict:
    sb = get_sb()
    res = (
        sb.table("device_project_links")
        .select("*")
        .eq("device_id", device_id)
        .eq("project_id", project_id)
        .limit(1)
        .execute()
    )
    existing = _first_or_none(res)
    if existing:
        if local_path and existing.get("local_path") != local_path:
            sb.table("device_project_links").update({"local_path": local_path}).eq("id", existing["id"]).execute()
            return {**existing, "local_path": local_path}
        return existing
    link_id = str(uuid.uuid4())
    sb.table("device_project_links").insert({
        "id": link_id,
        "device_id": device_id,
        "project_id": project_id,
        "local_path": local_path,
    }).execute()
    return {"id": link_id, "device_id": device_id, "project_id": project_id, "local_path": local_path}


def _link_device_project_local_path_if_missing(*, device_id: str, project_id: str, local_path: str) -> None:
    """
    Set device_project_links.local_path to `local_path` only when it's currently empty/missing.
    This avoids overwriting user-customized local paths.
    """
    sb = get_sb()
    res = (
        sb.table("device_project_links")
        .select("id, local_path")
        .eq("device_id", device_id)
        .eq("project_id", project_id)
        .limit(1)
        .execute()
    )
    existing = _first_or_none(res)

    if existing:
        if not existing.get("local_path"):
            sb.table("device_project_links").update({"local_path": local_path}).eq("id", existing["id"]).execute()
        return

    link_id = str(uuid.uuid4())
    sb.table("device_project_links").insert({
        "id": link_id,
        "device_id": device_id,
        "project_id": project_id,
        "local_path": local_path,
    }).execute()


def link_device_project_local_path_if_missing_for_user_devices(*, user_id: str, project_id: str, local_path: str) -> None:
    devices = list_devices_for_user(user_id)
    for d in devices:
        _link_device_project_local_path_if_missing(
            device_id=d["id"],
            project_id=project_id,
            local_path=local_path,
        )


def get_device_project_links(device_id: str) -> list[dict]:
    sb = get_sb()
    res = (
        sb.table("device_project_links")
        .select("*")
        .eq("device_id", device_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def save_cursor_context(
    *,
    device_id: str,
    project_id: str,
    file_path: str | None,
    selection: str | None,
    diagnostics: str | None,
) -> str:
    sb = get_sb()
    context_id = str(uuid.uuid4())
    sb.table("cursor_context_snapshots").insert({
        "id": context_id,
        "device_id": device_id,
        "project_id": project_id,
        "file_path": file_path,
        "selection": selection,
        "diagnostics": diagnostics,
    }).execute()
    return context_id


def get_latest_cursor_context(*, device_id: str, project_id: str) -> dict | None:
    sb = get_sb()
    return _execute_single(
        sb.table("cursor_context_snapshots")
        .select("*")
        .eq("device_id", device_id)
        .eq("project_id", project_id)
        .order("created_at", desc=True)
    )


# ==================== USER DATA DELETION ====================

def delete_user_history(user_id: str) -> dict:
    """
    Deletes user-owned activity data (not the Supabase account).
    Returns counts for confirmation UI.
    """
    sb = get_sb()
    res = sb.rpc("delete_user_history", {"p_user_id": user_id}).execute()
    return res.data if res.data else {}
