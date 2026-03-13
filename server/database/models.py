from __future__ import annotations

# server/database/models.py
"""Database operations via Supabase PostgREST client."""
from database.supabase_client import get_sb
import uuid
import json
from datetime import datetime, timezone
import hashlib
import secrets


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==================== USERS ====================

def upsert_user(user_id: str, email: str, phone_number: str | None = None):
    sb = get_sb()
    data = {"id": user_id, "email": email}
    if phone_number:
        data["phone_number"] = phone_number
    try:
        sb.table("users").upsert(data, on_conflict="id").execute()
    except Exception:
        sb.table("users").upsert(data, on_conflict="email").execute()
    print(f"[DB] upsert_user user_id={user_id} email={email!r} phone={phone_number!r}")


# ==================== PROJECTS ====================

def create_project(user_id, name, file_path=None):
    sb = get_sb()
    project_id = str(uuid.uuid4())
    sb.table("projects").insert({
        "id": project_id,
        "user_id": user_id,
        "name": name,
        "file_path": file_path,
    }).execute()
    print(f"[DB] create_project id={project_id} user_id={user_id} name={name!r}")
    return project_id


def touch_project(project_id: str):
    sb = get_sb()
    sb.table("projects").update({"last_accessed": _now_iso()}).eq("id", project_id).execute()
    print(f"[DB] touch_project project_id={project_id}")


def get_user_projects(user_id):
    sb = get_sb()
    res = sb.table("projects").select("*").eq("user_id", user_id).order("last_accessed", desc=True).execute()
    return res.data or []


def get_project_by_id(project_id):
    sb = get_sb()
    res = sb.table("projects").select("*").eq("id", project_id).maybe_single().execute()
    return res.data if res else None


def get_project_by_name(user_id, name):
    sb = get_sb()
    res = sb.table("projects").select("*").eq("user_id", user_id).ilike("name", name).maybe_single().execute()
    return res.data if res else None


def upsert_project_by_name(*, user_id: str, name: str, file_path: str | None = None) -> dict:
    existing = get_project_by_name(user_id, name)
    if existing:
        if file_path and (existing.get("file_path") != file_path):
            sb = get_sb()
            sb.table("projects").update({
                "file_path": file_path,
                "last_accessed": _now_iso(),
            }).eq("id", existing["id"]).execute()
            existing["file_path"] = file_path
        return existing

    project_id = create_project(user_id, name, file_path=file_path)
    p = get_project_by_id(project_id)
    return p or {"id": project_id, "user_id": user_id, "name": name, "file_path": file_path}


def get_user_projects_with_task_counts(user_id):
    sb = get_sb()
    res = sb.rpc("get_user_projects_with_task_counts", {"p_user_id": user_id}).execute()
    return res.data or []


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
    sb = get_sb()
    res = sb.table("tasks").select("*, projects(name)").eq("user_id", user_id).order("created_at", desc=True).execute()
    rows = res.data or []
    # Flatten: {projects: {name: "foo"}} → {project_name: "foo"}
    for row in rows:
        proj = row.pop("projects", None)
        row["project_name"] = proj.get("name") if proj else None
    print(f"[DB] get_user_tasks user_id={user_id} count={len(rows)}")
    return rows


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
    res = sb.table("tasks").select("*").eq("id", task_id).maybe_single().execute()
    return res.data if res else None


def set_task_terminal_session(task_id: str, terminal_session_id: str | None) -> None:
    sb = get_sb()
    sb.table("tasks").update({"terminal_session_id": terminal_session_id}).eq("id", task_id).execute()


# ==================== CALL SESSIONS ====================

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
    print(f"[DB] update_agent_execution id={exec_id} status={status}")


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
    print(f"[DB] store_agent_feedback task_id={task_id} status={status}")


def get_agent_executions(task_id: str) -> list:
    sb = get_sb()
    res = sb.table("agent_executions").select("*").eq("task_id", task_id).order("created_at").execute()
    return res.data or []


def get_task_agent_status(task_id: str) -> dict:
    sb = get_sb()
    res = sb.table("agent_executions").select("*").eq("task_id", task_id).order("created_at", desc=True).limit(1).maybe_single().execute()
    return (res.data if res else None) or {"status": "none", "stage": "none"}


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
    rows = res.data or []
    # Flatten nested task/project info
    for row in rows:
        task_info = row.pop("tasks", None)
        if task_info:
            row["task_description"] = task_info.get("description")
            proj = task_info.get("projects")
            row["project_name"] = proj.get("name") if proj else None
        else:
            row["task_description"] = None
            row["project_name"] = None
    return rows


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
    sb = get_sb()
    existing = None
    if instance_token:
        res = (
            sb.table("instances")
            .select("*")
            .eq("project_id", project_id)
            .eq("instance_token", instance_token)
            .limit(1)
            .maybe_single()
            .execute()
        )
        existing = res.data if res else None

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
        sb.table("instances").update(update_data).eq("id", instance_id).execute()
    else:
        instance_id = str(uuid.uuid4())
        sb.table("instances").insert({
            "id": instance_id,
            "user_id": user_id,
            "project_id": project_id,
            "pid": pid,
            "instance_token": instance_token,
            "metadata": json.dumps(metadata or {}),
            "status": status,
        }).execute()

    res = sb.table("instances").select("*").eq("id", instance_id).maybe_single().execute()
    return (res.data if res else None) or {"id": instance_id}


def get_instance_by_id(instance_id: str) -> dict | None:
    sb = get_sb()
    res = sb.table("instances").select("*").eq("id", instance_id).maybe_single().execute()
    return res.data if res else None


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
    res = sb.table("terminal_sessions").select("*").eq("id", session_id).maybe_single().execute()
    return res.data if res else None


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


def create_terminal_command(*, session_id: str, user_id: str, command: str) -> str:
    sb = get_sb()
    command_id = str(uuid.uuid4())
    sb.table("terminal_commands").insert({
        "id": command_id,
        "session_id": session_id,
        "user_id": user_id,
        "command": command,
        "status": "queued",
    }).execute()
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
    return res.data or []


def get_terminal_command(command_id: str) -> dict | None:
    sb = get_sb()
    res = sb.table("terminal_commands").select("*").eq("id", command_id).maybe_single().execute()
    return res.data if res else None


def claim_next_queued_command_for_instance(*, instance_id: str) -> dict | None:
    sb = get_sb()
    res = sb.rpc("claim_next_queued_command", {"p_instance_id": instance_id}).execute()
    rows = res.data or []
    return rows[0] if rows else None


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
        .maybe_single()
        .execute()
    )
    data = res.data if res else None
    if not data:
        return None
    token_id = data["id"]
    user_id = data["user_id"]
    sb.table("agent_tokens").update({"last_used_at": _now_iso()}).eq("id", token_id).execute()
    return user_id


# ==================== USER DATA DELETION ====================

def delete_user_history(user_id: str) -> dict:
    sb = get_sb()
    res = sb.rpc("delete_user_history", {"p_user_id": user_id}).execute()
    return res.data if res.data else {}
