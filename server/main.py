from __future__ import annotations
import os
import shutil
import json
import asyncio
import logging
import threading
import time
import uuid
from typing import Annotated, Union, Optional
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel
from supabase import create_client, Client
from pydantic import BaseModel
from datetime import datetime

# NEW: load server/.env when running locally (uvicorn doesn't auto-load it)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception as e:
    pass

DEVELOPMENT_MODE = os.environ.get("DEVELOPMENT_MODE", "true").lower() == "true"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


class AccessLogThrottleFilter(logging.Filter):
    """
    Keep useful access logs while suppressing repetitive high-frequency noise.
    - Drops OPTIONS requests.
    - Throttles repeated 200 logs for polling endpoints.
    """

    def __init__(self, window_s: float = 10.0):
        super().__init__()
        self.window_s = window_s
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()
        self.noisy_paths = (
            "/api/agent/local/claim-next",
            "/api/agent/local/heartbeat",
            "/api/agent/executions/",
            "/api/terminal/commands/",
            "/api/terminal/sessions/",
        )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "OPTIONS " in msg:
            return False

        is_noisy = any(p in msg for p in self.noisy_paths)
        is_ok = '" 200 OK' in msg
        if not (is_noisy and is_ok):
            return True

        key = msg.split("HTTP/1.1")[0] if "HTTP/1.1" in msg else msg
        now = time.time()
        with self._lock:
            last = self._last_seen.get(key, 0.0)
            if now - last < self.window_s:
                return False
            self._last_seen[key] = now
        return True


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("callstack.api")
db_logger = logging.getLogger("callstack.db")

uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(AccessLogThrottleFilter(window_s=10.0))

for key, value in os.environ.items():
    if "SUPABASE" in key or "NEXT_PUBLIC" in key:
        masked_value = value[:10] + "..." if len(value) > 10 else value
        logger.debug("env %s=%s", key, masked_value)

# --- LOCAL IMPORTS ---
from database.connection import init_database
from database import models
from services.llm import parse_intent
from agents.copilot_agent import dispatch_task as agent_dispatch_task
from agents.copilot_agent import set_terminal_access, get_terminal_access

app = FastAPI(title="CallStack API")

# --- CONFIG ---
SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")

logger.info(
    "startup env development=%s supabase_url_set=%s service_key_set=%s",
    DEVELOPMENT_MODE,
    bool(SUPABASE_URL),
    bool(SUPABASE_SERVICE_KEY),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. DATABASE INITIALIZATION ---
@app.on_event("startup")
def on_startup():
    """Initialize the SQLite database when server starts"""
    init_database()

# --- 2. GLOBAL STATE (WHISPER) ---
logger.info("loading whisper model")
model = WhisperModel("tiny", device="cpu", compute_type="int8")
logger.info("whisper model loaded")


@app.middleware("http")
async def request_trace_middleware(request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_id=%s uncaught error path=%s", request_id, request.url.path)
        raise

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    # Structured app logs for debugging; keep noisy paths at debug level.
    is_noisy = (
        request.url.path.startswith("/api/agent/local/claim-next")
        or request.url.path.startswith("/api/agent/local/heartbeat")
        or request.url.path.startswith("/api/agent/executions/")
        or request.url.path.startswith("/api/terminal/commands/")
    )
    level = logging.DEBUG if is_noisy and response.status_code < 400 else logging.INFO
    logger.log(
        level,
        "request_id=%s method=%s path=%s status=%s elapsed_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    response.headers["x-request-id"] = request_id
    return response

# --- 3. SECURITY ---
def get_current_user(authorization: Annotated[Union[str, None], Header()] = None):
    """
    Validates the Supabase JWT. Returns the Supabase User object.
    In DEVELOPMENT_MODE: if a JWT is provided, use it; otherwise fall back to a mock user.
    """
    # If a real token is present, always honor it (even in dev mode)
    has_auth = bool(authorization)

    if has_auth:
        # If client sent a JWT, we must be able to validate it. Otherwise fail loudly.
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise HTTPException(
                status_code=500,
                detail="Supabase server env not configured (SUPABASE_URL/SUPABASE_SERVICE_KEY). Check server/.env loading.",
            )

        try:
            if " " in authorization:
                token = authorization.split(" ")[1]
            else:
                token = authorization
            supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            user_response = supabase.auth.get_user(token)
            u = user_response.user
            return u
        except Exception as e:
            logger.warning("supabase auth failed err=%r", e)
            raise HTTPException(status_code=401, detail="Invalid or Expired Token")

    # No token (or token invalid in dev): allow mock user only in dev mode
    if DEVELOPMENT_MODE:
        class MockUser:
            id = os.environ.get("DEV_USER_ID", "test-user-123")
            email = os.environ.get("DEV_USER_EMAIL", "test@example.com")
            phone = os.environ.get("DEV_USER_PHONE", "+15551234567")
        return MockUser()

    raise HTTPException(status_code=401, detail="Missing Authorization Header")


def get_current_agent_user_id(
    x_agent_token: Annotated[Union[str, None], Header(alias="X-Agent-Token")] = None,
) -> str:
    """
    Auth for local agents (no Supabase JWT required).
    """
    if not x_agent_token:
        raise HTTPException(status_code=401, detail="Missing X-Agent-Token")
    user_id = models.get_user_id_for_agent_token(x_agent_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid agent token")
    return user_id

# --- 4. REQUEST MODELS ---
class CreateProjectRequest(BaseModel):
    user_id: str
    name: str
    file_path: str = None

class CreateTaskRequest(BaseModel):
    project_id: str
    description: str
    # allow client/dashboard-created tasks to attach user_id explicitly
    user_id: Optional[str] = None

class UpdateTaskRequest(BaseModel):
    status: str

class RegisterLocalAgentRequest(BaseModel):
    project_id: str | None = None
    project_name: str | None = None
    project_path: str | None = None
    instance_token: str | None = None
    pid: int | None = None
    metadata: dict | None = None

class LocalAgentHeartbeatRequest(BaseModel):
    instance_id: str
    status: str = "online"

class CreateTerminalSessionRequest(BaseModel):
    project_id: str
    name: str | None = None
    instance_id: str | None = None

class CreateTerminalCommandRequest(BaseModel):
    command: str

class AppendTerminalLogsRequest(BaseModel):
    sequence_start: int
    stream: str  # 'stdout' | 'stderr'
    chunks: list[str]

class CompleteTerminalCommandRequest(BaseModel):
    status: str  # 'completed' | 'failed' | 'cancelled'
    exit_code: int | None = None

class ClaimNextCommandRequest(BaseModel):
    instance_id: str
    wait_seconds: int = 20

class CreateAgentTokenRequest(BaseModel):
    label: str | None = None

def _require_project_owner(user_id: str, project_id: str) -> dict:
    project = models.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return project

def _require_terminal_session_owner(user_id: str, session_id: str) -> dict:
    session = models.get_terminal_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Terminal session not found")
    if session.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return session

def _require_terminal_command_owner(user_id: str, command_id: str) -> dict:
    cmd = models.get_terminal_command(command_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Terminal command not found")
    if cmd.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return cmd


@app.post("/api/settings/agent-tokens")
async def create_agent_token(request: CreateAgentTokenRequest, user: dict = Depends(get_current_user)):
    models.upsert_user(user_id=user.id, email=getattr(user, "email", None) or f"{user.id}@local", phone_number=getattr(user, "phone", None))
    token = models.create_agent_token(user_id=user.id, label=request.label)
    return {"success": True, **token}


@app.get("/api/settings/agent-tokens")
async def list_agent_tokens(user: dict = Depends(get_current_user)):
    tokens = models.list_agent_tokens(user_id=user.id)
    return {"success": True, "tokens": tokens}


@app.delete("/api/settings/agent-tokens/{token_id}")
async def revoke_agent_token(token_id: str, user: dict = Depends(get_current_user)):
    models.revoke_agent_token(user_id=user.id, token_id=token_id)
    return {"success": True}


@app.delete("/api/settings/history")
async def delete_history(user: dict = Depends(get_current_user)):
    counts = models.delete_user_history(user_id=user.id)
    return {"success": True, "deleted": counts}

# --- 5. THE CORE ENDPOINT (EAR + BRAIN + HANDS) ---
@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...), 
    user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
):
    """
    1. Transcribes Audio (Whisper)
    2. Fetches Context (SQLite)
    3. Determines Intent (Bedrock)
    4. Executes Action (SQLite)
    5. Dispatches to Agent Pipeline (Background)
    """
    try:
        logger.info("transcribe start user_id=%s filename=%s", getattr(user, "id", None), file.filename)

        # Ensure a corresponding users row exists (id comes from Supabase)
        models.upsert_user(
            user_id=user.id,
            email=getattr(user, "email", None) or f"{user.id}@local",
            phone_number=getattr(user, "phone", None),
        )

        # A. Transcribe
        logger.debug("transcribe step=a")
        temp_filename = f"temp_{file.filename}"
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        segments, info = model.transcribe(temp_filename, beam_size=5)
        transcript_text = " ".join([segment.text for segment in segments]).strip()
        os.remove(temp_filename)
        logger.debug("transcribe text_len=%s", len(transcript_text))
        
        # B. Context
        logger.debug("transcribe step=b")
        user_projects = models.get_user_projects(user.id)
        logger.debug("transcribe projects_count=%s", len(user_projects))
        # C. Parse Intent
        logger.debug("transcribe step=c")
        intent_data = await parse_intent(transcript_text, user_projects) or {"intent": "unknown"}
        logger.debug("transcribe intent=%s", intent_data.get("intent"))
        
        # Normalize for storage
        intent_type = intent_data.get("intent") or "unknown"
        project_name = intent_data.get("project_name")
        task_description = intent_data.get("task_description")
        logger.info("transcribe intent_type=%s project_name=%r", intent_type, project_name)

        action_result = None
        created = {"project_id": None, "task_id": None}
        
        # --- HANDLER: CREATE PROJECT ---
        if intent_type == "create_project":
            new_project_name = project_name
            if new_project_name:
                created["project_id"] = models.create_project(user.id, new_project_name)
                action_result = f"Successfully created project '{new_project_name}'."
                logger.info("transcribe created_project_id=%s", created["project_id"])
            else:
                action_result = "I couldn't determine a project name."
        
        # --- HANDLER: CREATE TASK ---
        elif intent_type == "create_task":
            if project_name and task_description:
                project = models.get_project_by_name(user.id, project_name)
                logger.debug("transcribe project_lookup found=%s", bool(project))
                if project:
                    models.touch_project(project["id"])
                    created["task_id"] = models.create_task(
                        project_id=project["id"],
                        user_id=user.id,
                        description=task_description,
                        voice_command=transcript_text,
                        raw_transcript=transcript_text,
                        intent_type=intent_type,
                        intent_confidence=None,
                        output_summary=None,
                    )
                    action_result = f"Created task '{task_description}' in project '{project_name}'."
                    logger.info("transcribe created_task_id=%s project_id=%s", created["task_id"], project["id"])
                else:
                    action_result = f"Could not find a project named '{project_name}'."
            else:
                action_result = "I couldn't determine the project or task from your command."

        # --- HANDLER: STATUS CHECK ---
        elif intent_type == "status_check":
            projects_with_counts = models.get_user_projects_with_task_counts(user.id)
            if not projects_with_counts:
                action_result = "You don't have any projects yet. Try saying 'create a project called my-app'."
            else:
                lines = [f"You have {len(projects_with_counts)} project(s):"]
                for p in projects_with_counts:
                    total = p["total_tasks"] or 0
                    pending = p["pending_tasks"] or 0
                    in_prog = p["in_progress_tasks"] or 0
                    done = p["completed_tasks"] or 0
                    lines.append(f"  '{p['name']}' — {total} task(s) ({pending} pending, {in_prog} in progress, {done} done)")
                action_result = "\n".join(lines)
            logger.debug("transcribe status_check")

        else:
            action_result = "I wasn't able to map that command to an action."
            logger.debug("transcribe unknown intent")

        # Always store a task row for auditability of agent parsing (even if unknown)
        logged_task_id = models.log_agent_event_task(
            user_id=user.id,
            project_name=project_name,
            projects=user_projects,
            description=task_description or f"[{intent_type}] {transcript_text}".strip(),
            raw_transcript=transcript_text,
            intent_type=intent_type,
            intent_confidence=None,
            output_summary=action_result,
            voice_command=transcript_text,
        )
        logger.info("transcribe logged_task_id=%s user_id=%s", logged_task_id, user.id)

        # --- D. DISPATCH TO AGENT PIPELINE (background) ---
        dispatch_task_id = created.get("task_id") or logged_task_id
        agent_status = None
        terminal_granted = get_terminal_access(user.id)
        if intent_type in ("create_task", "create_project", "fix_bug") and dispatch_task_id:
            if background_tasks:
                background_tasks.add_task(agent_dispatch_task, dispatch_task_id, intent_data, terminal_granted)
                agent_status = "dispatching"
                logger.info("agent dispatch queued task_id=%s terminal=%s", dispatch_task_id, terminal_granted)
            else:
                # Fallback: run synchronously
                try:
                    pipeline_result = agent_dispatch_task(dispatch_task_id, intent_data, terminal_granted)
                    agent_status = pipeline_result.get("status", "unknown")
                except Exception as ae:
                    agent_status = f"dispatch_error: {ae}"
                    logger.warning("agent dispatch error task_id=%s err=%r", dispatch_task_id, ae)

        return {
            "status": "success",
            "transcript": transcript_text,
            "intent": intent_data,
            "action_result": action_result,
            "context_projects_count": len(user_projects),
            "created": created,
            "logged_task_id": logged_task_id,
            "agent_status": agent_status,
            "terminal_access": terminal_granted,
        }

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error("transcribe pipeline error=%r", e)
        logger.debug("transcribe traceback=%s", error_trace)
        return {"status": "error", "message": str(e), "traceback": error_trace}

# --- 6. CRUD ENDPOINTS (For Dashboard) ---

@app.get("/api/dashboard/{user_id}")
async def get_dashboard(user_id: str):
    projects = models.get_user_projects_with_task_counts(user_id)
    tasks = models.get_user_tasks(user_id)
    logger.debug("dashboard user_id=%s projects=%s tasks=%s", user_id, len(projects), len(tasks))
    return {
        "success": True,
        "projects": projects,
        "tasks": tasks,
    }

@app.get("/api/projects/{user_id}")
async def get_user_projects(user_id: str):
    return {"success": True, "projects": models.get_user_projects(user_id)}

@app.post("/api/projects")
async def create_project(request: CreateProjectRequest):
    models.upsert_user(user_id=request.user_id, email=f"{request.user_id}@local", phone_number=None)
    pid = models.create_project(request.user_id, request.name, request.file_path)
    return {"success": True, "project_id": pid}

@app.get("/api/projects/{project_id}/tasks")
async def get_project_tasks(project_id: str):
    return {"success": True, "tasks": models.get_project_tasks(project_id)}

@app.post("/api/tasks")
async def create_task(request: CreateTaskRequest):
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    tid = models.create_task(request.project_id, request.user_id, request.description)
    return {"success": True, "task_id": tid}

@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: str, request: UpdateTaskRequest):
    models.update_task_status(task_id, request.status)
    return {"success": True, "message": "Task updated"}

@app.get("/api/call-sessions/{user_id}")
async def get_call_history(user_id: str):
    sessions = models.get_user_call_history(user_id, limit=20)
    return {"success": True, "sessions": sessions}

# --- 7. AGENT PIPELINE ENDPOINTS ---

@app.get("/api/agent/status/{task_id}")
async def get_agent_status(task_id: str):
    """Get agent pipeline status for a specific task."""
    executions = models.get_agent_executions(task_id)
    latest = models.get_task_agent_status(task_id)
    return {
        "success": True,
        "task_id": task_id,
        "latest": latest,
        "executions": executions,
    }


@app.get("/api/agent/executions/{user_id}")
async def get_user_agent_executions(user_id: str):
    """Get all agent executions for a user."""
    executions = models.get_user_agent_executions(user_id)
    return {
        "success": True,
        "executions": executions,
    }


@app.post("/api/agent/dispatch/{task_id}")
async def manually_dispatch_agent(task_id: str, background_tasks: BackgroundTasks):
    """Manually trigger agent dispatch for a task."""
    from database.connection import get_db_connection
    conn = get_db_connection()
    task_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    if not task_row:
        raise HTTPException(status_code=404, detail="Task not found")
    task_dict = dict(task_row)
    intent_data = {
        "intent": task_dict.get("intent_type", "create_task"),
        "project_name": None,
        "task_description": task_dict.get("description", ""),
    }
    # Get project name
    if task_dict.get("project_id"):
        project = models.get_project_by_id(task_dict["project_id"])
        if project:
            intent_data["project_name"] = project["name"]

    user_id = task_dict.get("user_id", "")
    terminal_granted = get_terminal_access(user_id)
    background_tasks.add_task(agent_dispatch_task, task_id, intent_data, terminal_granted)
    return {"success": True, "message": "Agent pipeline dispatched", "task_id": task_id, "terminal_access": terminal_granted}


# --- 8. TERMINAL ACCESS ENDPOINTS ---

@app.post("/api/agent/terminal-access/{user_id}")
async def grant_terminal_access(user_id: str):
    """User grants permission for auto-terminal execution."""
    set_terminal_access(user_id, True)
    return {"success": True, "terminal_access": True, "message": "Terminal access granted. Tasks will auto-execute in terminal."}


@app.delete("/api/agent/terminal-access/{user_id}")
async def revoke_terminal_access(user_id: str):
    """User revokes terminal execution permission."""
    set_terminal_access(user_id, False)
    return {"success": True, "terminal_access": False, "message": "Terminal access revoked."}


@app.get("/api/agent/terminal-access/{user_id}")
async def check_terminal_access(user_id: str):
    """Check if user has granted terminal access."""
    granted = get_terminal_access(user_id)
    return {"success": True, "terminal_access": granted}


# --- 9. LOCAL AGENT (USER MACHINE) ENDPOINTS ---

@app.post("/api/agent/local/register")
async def register_local_agent(
    request: RegisterLocalAgentRequest,
    agent_user_id: str = Depends(get_current_agent_user_id),
):
    """
    Register a local helper/daemon instance for a project.
    Auth: Supabase JWT (same as browser); in the future can be API keys.
    """
    project_id = request.project_id
    if project_id:
        _require_project_owner(agent_user_id, project_id)
    else:
        # Create (or reuse) project automatically for minimal user friction
        inferred_name = (request.project_name or "").strip()
        if not inferred_name and request.project_path:
            inferred_name = os.path.basename(request.project_path.rstrip("/")) or "Local Project"
        if not inferred_name:
            inferred_name = "Local Project"
        project = models.upsert_project_by_name(
            user_id=agent_user_id,
            name=inferred_name,
            file_path=request.project_path,
        )
        project_id = project["id"]

    row = models.register_instance(
        user_id=agent_user_id,
        project_id=project_id,
        instance_token=request.instance_token,
        pid=request.pid,
        status="online",
        metadata=request.metadata or {},
    )
    return {"success": True, "project_id": project_id, "instance": row}


@app.post("/api/agent/local/heartbeat")
async def local_agent_heartbeat(
    request: LocalAgentHeartbeatRequest,
    agent_user_id: str = Depends(get_current_agent_user_id),
):
    # Ensure the instance belongs to the same user (best-effort)
    inst = None
    try:
        from database.connection import get_db_connection
        conn = get_db_connection()
        r = conn.execute("SELECT * FROM instances WHERE id = ?", (request.instance_id,)).fetchone()
        conn.close()
        inst = dict(r) if r else None
    except Exception:
        inst = None
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    if inst.get("user_id") and inst.get("user_id") != agent_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    models.update_instance_heartbeat(instance_id=request.instance_id, status=request.status)
    return {"success": True, "instance_id": request.instance_id, "status": request.status, "ts": datetime.utcnow().isoformat()}


@app.post("/api/agent/local/claim-next")
async def local_agent_claim_next(
    request: ClaimNextCommandRequest,
    agent_user_id: str = Depends(get_current_agent_user_id),
):
    """
    Local helper pulls the next queued command for sessions bound to its instance.
    """
    # Basic ownership check
    from database.connection import get_db_connection
    conn = get_db_connection()
    r = conn.execute("SELECT * FROM instances WHERE id = ?", (request.instance_id,)).fetchone()
    conn.close()
    if not r:
        raise HTTPException(status_code=404, detail="Instance not found")
    inst = dict(r)
    if inst.get("user_id") and inst["user_id"] != agent_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    wait_s = max(0, min(request.wait_seconds, 30))
    cmd = models.claim_next_queued_command_for_instance(instance_id=request.instance_id)
    if not cmd and wait_s > 0:
        deadline = asyncio.get_running_loop().time() + wait_s
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.5)
            cmd = models.claim_next_queued_command_for_instance(instance_id=request.instance_id)
            if cmd:
                break
    return {"success": True, "command": cmd}


@app.post("/api/agent/local/commands/{command_id}/append-logs")
async def local_agent_append_logs(
    command_id: str,
    request: AppendTerminalLogsRequest,
    agent_user_id: str = Depends(get_current_agent_user_id),
):
    _require_terminal_command_owner(agent_user_id, command_id)
    seq = request.sequence_start
    for chunk in request.chunks:
        models.append_terminal_log_chunk(command_id=command_id, sequence=seq, stream=request.stream, chunk=chunk)
        seq += 1
    return {"success": True, "next_sequence": seq}


@app.post("/api/agent/local/commands/{command_id}/complete")
async def local_agent_complete_command(
    command_id: str,
    request: CompleteTerminalCommandRequest,
    agent_user_id: str = Depends(get_current_agent_user_id),
):
    _require_terminal_command_owner(agent_user_id, command_id)
    if request.status not in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status")
    models.complete_terminal_command(command_id=command_id, status=request.status, exit_code=request.exit_code)
    return {"success": True}


# --- 10. TERMINAL (WEB UI) ENDPOINTS ---

@app.get("/api/terminal/sessions/{project_id}")
async def list_terminal_sessions(project_id: str, user: dict = Depends(get_current_user)):
    _require_project_owner(user.id, project_id)
    sessions = models.list_terminal_sessions_for_project(user_id=user.id, project_id=project_id)
    return {"success": True, "sessions": sessions}


@app.post("/api/terminal/sessions")
async def create_terminal_session(request: CreateTerminalSessionRequest, user: dict = Depends(get_current_user)):
    _require_project_owner(user.id, request.project_id)

    instance_id = request.instance_id
    if not instance_id:
        active = models.get_active_instances_for_project(request.project_id, within_seconds=120)
        instance_id = active[0]["id"] if active else None

    session_id = models.create_terminal_session(
        user_id=user.id,
        project_id=request.project_id,
        name=request.name,
        instance_id=instance_id,
        status="pending" if instance_id else "pending",
    )
    return {"success": True, "session_id": session_id, "instance_id": instance_id}


@app.delete("/api/terminal/sessions/{session_id}")
async def close_terminal_session(session_id: str, user: dict = Depends(get_current_user)):
    _require_terminal_session_owner(user.id, session_id)
    models.set_terminal_session_status(session_id, "closing", closed=False)
    return {"success": True}


@app.post("/api/terminal/sessions/{session_id}/commands")
async def create_terminal_command(session_id: str, request: CreateTerminalCommandRequest, user: dict = Depends(get_current_user)):
    session = _require_terminal_session_owner(user.id, session_id)
    if not session.get("instance_id"):
        # Try to auto-bind to latest active instance for this project.
        project_id = session.get("project_id")
        if project_id:
            active = models.get_active_instances_for_project(project_id, within_seconds=180)
            if active:
                models.bind_terminal_session_instance(session_id, active[0]["id"])
                session = _require_terminal_session_owner(user.id, session_id)
        if not session.get("instance_id"):
            raise HTTPException(status_code=409, detail="No local agent connected for this session")
    command_id = models.create_terminal_command(session_id=session_id, user_id=user.id, command=request.command)
    return {"success": True, "command_id": command_id}


@app.get("/api/terminal/sessions/{session_id}/commands")
async def list_terminal_commands(session_id: str, user: dict = Depends(get_current_user)):
    _require_terminal_session_owner(user.id, session_id)
    cmds = models.list_terminal_commands_for_session(user_id=user.id, session_id=session_id, limit=200)
    return {"success": True, "commands": cmds}


@app.get("/api/terminal/commands/{command_id}/logs")
async def get_terminal_command_logs(
    command_id: str,
    after_sequence: int | None = None,
    limit: int = 200,
    user: dict = Depends(get_current_user),
):
    _require_terminal_command_owner(user.id, command_id)
    logs = models.get_terminal_logs_for_command(command_id=command_id, after_sequence=after_sequence, limit=limit)
    return {"success": True, "logs": logs}


@app.get("/")
async def root():
    return {"status": "CallStack Agent is Listening..."}

@app.get("/health")
async def health():
    return {"status": "healthy"}
