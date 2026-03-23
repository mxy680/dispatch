from __future__ import annotations
import os
import shutil
import json
import asyncio
import logging
import threading
import time
import uuid
from typing import Annotated, Union, Optional, Literal
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends, BackgroundTasks
from fastapi import Response, Request
from fastapi.middleware.cors import CORSMiddleware
from services.transcription import transcribe_file
from supabase import create_client, Client
from pydantic import BaseModel
from datetime import datetime

# NEW: load server/.env when running locally (uvicorn doesn't auto-load it)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception as e:
    pass
os.environ['DEVELOPMENT_MODE']='true'
DEVELOPMENT_MODE = os.environ.get("DEVELOPMENT_MODE", "true").lower() == "true"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
os.environ['AWS_PROFILE'] = "personal"

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
            "/api/device/claim-next",
            "/api/device/heartbeat",
            "/api/agent/local/claim-next",
            "/api/agent/local/heartbeat",
            "/api/agent/executions/",
            "/api/terminal/commands/",
            "/api/terminal/sessions/",
            "/api/unified/timeline",
            "/api/terminal/commands/",      # list + logs
            "/api/terminal/sessions/",      # polling
            "/api/call-sessions/",          # if it’s chatty
        )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "OPTIONS " in msg:
            return False
        # If it's one of the noisy endpoints and succeeded, drop it completely
        if any(p in msg for p in self.noisy_paths) and '" 200 OK' in msg:
            return False

        # Otherwise, keep the log
        return True
        # is_noisy = any(p in msg for p in self.noisy_paths)
        # is_ok = '" 200 OK' in msg
        # if not (is_noisy and is_ok):
        #     return True

        # key = msg.split("HTTP/1.1")[0] if "HTTP/1.1" in msg else msg
        # now = time.time()
        # with self._lock: 
        #     last = self._last_seen.get(key, 0.0)
        #     if now - last < self.window_s:
        #         return False
        #     self._last_seen[key] = now
        # return True


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("callstack.api")
db_logger = logging.getLogger("callstack.db")

uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(AccessLogThrottleFilter(window_s=10.0))

if DEVELOPMENT_MODE:
    for key, value in os.environ.items():
        if "SUPABASE" in key or "NEXT_PUBLIC" in key:
            masked_value = value[:10] + "..." if len(value) > 10 else value
            logger.debug("env %s=%s", key, masked_value)

# --- LOCAL IMPORTS ---
from database import models
from services.llm import parse_intent
from services import phone_verification
from agents.dispatcher import dispatch_task as agent_dispatch_task
from agents.dispatcher import set_terminal_access, get_terminal_access

app = FastAPI(title="Dispatch API")

# --- CONFIG ---
SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")

logger.info(
    "startup env development=%s supabase_url_set=%s service_key_set=%s",
    DEVELOPMENT_MODE,
    bool(SUPABASE_URL),
    bool(SUPABASE_SERVICE_KEY),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3100"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. DATABASE (Supabase — no local init needed) ---

# --- 2. GLOBAL STATE ---
# Transcription now uses Groq's Whisper API (no local model needed)


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
    # Structured app logs for debugging; keep polling/noisy paths at debug level.
    is_noisy = (
        request.url.path.startswith("/api/device/claim-next")
        or request.url.path.startswith("/api/device/heartbeat")
        or request.url.path.startswith("/api/device/my-projects")
        or request.url.path.startswith("/api/device/commands/")
        or request.url.path.startswith("/api/device/cursor-context")
        or request.url.path.startswith("/api/agent/local/claim-next")
        or request.url.path.startswith("/api/agent/local/heartbeat")
        or request.url.path.startswith("/api/agent/executions/")
        or request.url.path.startswith("/api/terminal/commands/")
        or request.url.path.startswith("/api/unified/timeline")
    )
    # Avoid spamming INFO for 401 polling failures; still keep errors visible.
    if is_noisy:
        level = logging.DEBUG if response.status_code < 500 else logging.WARNING
    else:
        level = logging.INFO
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
            phone = os.environ.get("DEV_USER_PHONE", None)
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


def get_current_device(
    x_device_token: Annotated[Union[str, None], Header(alias="X-Device-Token")] = None,
) -> dict:
    if not x_device_token:
        raise HTTPException(status_code=401, detail="Missing X-Device-Token")
    device = models.get_device_by_token(x_device_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid device token")
    return device

# --- 4. REQUEST MODELS ---
class CreateProjectRequest(BaseModel):
    user_id: str
    name: str
    file_path: str | None = None

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
    provider: Literal["cursor", "claude", "shell"] | None = None

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


class UpdateProviderPreferenceRequest(BaseModel):
    provider: Literal["cursor", "claude", "shell"]


class UpdateProjectBasePathRequest(BaseModel):
    base_path: str | None = None


class UnifiedCommandRequest(BaseModel):
    project_id: str
    prompt: str
    source: Literal["typed", "system"] = "typed"
    provider: Literal["cursor", "claude", "shell"] | None = None
    session_name: str | None = "Unified Session"
    device_id: str | None = None


class DevicePairStartRequest(BaseModel):
    name: str | None = None
    platform: str | None = None


class DevicePairCompleteRequest(BaseModel):
    pairing_code: str
    name: str | None = None
    platform: str | None = None


class DeviceProjectLinkRequest(BaseModel):
    project_id: str
    local_path: str | None = None


class DeviceProjectLinkByNameRequest(BaseModel):
    project_name: str
    local_path: str


class DeviceHeartbeatRequest(BaseModel):
    device_id: str


class DeviceClaimRequest(BaseModel):
    wait_seconds: int = 20


class CursorContextRequest(BaseModel):
    project_id: str
    file_path: str | None = None
    selection: str | None = None
    diagnostics: str | None = None


class SendOtpRequest(BaseModel):
    phone_number: str


class VerifyOtpRequest(BaseModel):
    phone_number: str
    code: str


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


def _require_task_owner(user_id: str, task_id: str) -> dict:
    task = models.get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return task


def _require_user_match(path_user_id: str, user_id: str) -> None:
    if path_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")


def _require_device_owner(user_id: str, device_id: str) -> dict:
    devices = models.list_devices_for_user(user_id)
    dev = next((d for d in devices if d.get("id") == device_id), None)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    return dev


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


@app.get("/api/settings/provider")
async def get_provider_preference(user: dict = Depends(get_current_user)):
    provider = models.get_default_provider_for_user(user.id)
    return {"success": True, "provider": provider}


@app.put("/api/settings/provider")
async def set_provider_preference(
    request: UpdateProviderPreferenceRequest,
    user: dict = Depends(get_current_user),
):
    models.set_default_provider_for_user(user.id, request.provider)
    return {"success": True, "provider": request.provider}


@app.get("/api/settings/project-base-path")
async def get_project_base_path(user: dict = Depends(get_current_user)):
    return {"success": True, "base_path": models.get_project_base_path_for_user(user.id)}


@app.put("/api/settings/project-base-path")
async def set_project_base_path(
    request: UpdateProjectBasePathRequest,
    user: dict = Depends(get_current_user),
):
    models.set_project_base_path_for_user(user.id, request.base_path)
    return {"success": True, "base_path": models.get_project_base_path_for_user(user.id)}


@app.get("/api/settings/project-base-path")
async def get_project_base_path(user: dict = Depends(get_current_user)):
    return {"success": True, "base_path": models.get_project_base_path_for_user(user.id)}


@app.put("/api/settings/project-base-path")
async def set_project_base_path(
    request: UpdateProjectBasePathRequest,
    user: dict = Depends(get_current_user),
):
    models.set_project_base_path_for_user(user.id, request.base_path)
    return {"success": True, "base_path": models.get_project_base_path_for_user(user.id)}


import re as _re

_E164_RE = _re.compile(r"^\+[1-9]\d{1,14}$")


@app.post("/api/phone/send-otp")
async def send_otp(request: SendOtpRequest, user: dict = Depends(get_current_user)):
    if not _E164_RE.match(request.phone_number):
        raise HTTPException(status_code=400, detail="Phone number must be in E.164 format (e.g. +12125551234)")
    success = phone_verification.send_verification(request.phone_number)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to send verification code")
    return {"success": True}


@app.post("/api/phone/verify-otp")
async def verify_otp(request: VerifyOtpRequest, user: dict = Depends(get_current_user)):
    if not _E164_RE.match(request.phone_number):
        raise HTTPException(status_code=400, detail="Phone number must be in E.164 format (e.g. +12125551234)")
    approved = phone_verification.check_verification(request.phone_number, request.code)
    if not approved:
        return {"success": False, "error": "Invalid or expired verification code"}
    try:
        models.update_user_phone_number(user.id, request.phone_number)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    return {"success": True}


@app.get("/api/phone/status")
async def phone_status(user: dict = Depends(get_current_user)):
    phone_number = models.get_user_phone_number(user.id)
    return {"has_phone": bool(phone_number)}


@app.post("/api/device/pair/start")
async def start_device_pairing(request: DevicePairStartRequest, user: dict = Depends(get_current_user)):
    models.upsert_user(
        user_id=user.id,
        email=getattr(user, "email", None) or f"{user.id}@local",
        phone_number=getattr(user, "phone", None),
    )
    pairing = models.create_device_pairing(user_id=user.id, name=request.name, platform=request.platform)
    return {"success": True, **pairing}


@app.post("/api/device/pair/complete")
async def complete_device_pairing(request: DevicePairCompleteRequest):
    result = models.complete_device_pairing(
        pairing_code=request.pairing_code,
        device_name=request.name,
        platform=request.platform,
    )
    if not result:
        raise HTTPException(status_code=400, detail="Invalid or expired pairing code")

    user_id = result["user_id"]
    device_id = result["device_id"]
    user_projects = models.get_user_projects(user_id)
    base_path = models.get_project_base_path_for_user(user_id)
    for proj in user_projects:
        local_path = proj.get("file_path") or models.compute_default_project_file_path(base_path, proj.get("name") or "")
        if local_path:
            models.link_device_project(device_id=device_id, project_id=proj["id"], local_path=local_path)
        else:
            models.link_device_project(device_id=device_id, project_id=proj["id"])
    logger.info(
        "device paired device_id=%s user_id=%s auto_linked_projects=%s",
        device_id, user_id, len(user_projects),
    )
    return {"success": True, **result}


@app.get("/api/device")
async def list_user_devices(user: dict = Depends(get_current_user)):
    return {"success": True, "devices": models.list_devices_for_user(user.id)}


@app.post("/api/device/{device_id}/projects")
async def link_device_to_project(
    device_id: str,
    request: DeviceProjectLinkRequest,
    user: dict = Depends(get_current_user),
):
    _require_device_owner(user.id, device_id)
    _require_project_owner(user.id, request.project_id)
    linked = models.link_device_project(
        device_id=device_id,
        project_id=request.project_id,
        local_path=request.local_path,
    )
    return {"success": True, "link": linked}


@app.get("/api/device/{device_id}/projects")
async def list_device_projects(device_id: str, user: dict = Depends(get_current_user)):
    _require_device_owner(user.id, device_id)
    return {"success": True, "links": models.get_device_project_links(device_id)}


@app.get("/api/device/my-projects")
async def list_my_device_projects(device: dict = Depends(get_current_device)):
    """Device-token authenticated: returns project links for the calling device."""
    return {"success": True, "links": models.get_device_project_links(device["id"])}


@app.get("/api/device/settings/project-base-path")
async def get_device_project_base_path(device: dict = Depends(get_current_device)):
    return {"success": True, "base_path": models.get_project_base_path_for_user(device["user_id"])}


@app.put("/api/device/settings/project-base-path")
async def set_device_project_base_path(
    request: UpdateProjectBasePathRequest,
    device: dict = Depends(get_current_device),
):
    models.set_project_base_path_for_user(device["user_id"], request.base_path)
    return {"success": True, "base_path": models.get_project_base_path_for_user(device["user_id"])}


@app.post("/api/device/link-project")
async def link_project_for_current_device(
    request: DeviceProjectLinkByNameRequest,
    device: dict = Depends(get_current_device),
):
    """
    Device-token authenticated endpoint for companion setup:
    - upserts project by name for the device's user
    - links that project to this device with local_path
    """
    project_name = (request.project_name or "").strip()
    if not project_name:
        raise HTTPException(status_code=400, detail="project_name is required")
    local_path = (request.local_path or "").strip()
    if not local_path:
        raise HTTPException(status_code=400, detail="local_path is required")

    project = models.upsert_project_by_name(
        user_id=device["user_id"],
        name=project_name,
        file_path=local_path,
    )
    link = models.link_device_project(
        device_id=device["id"],
        project_id=project["id"],
        local_path=local_path,
    )
    return {"success": True, "project": project, "link": link}


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

        # A. Transcribe via Groq Whisper API
        logger.debug("transcribe step=a")
        import tempfile as _tempfile
        with _tempfile.NamedTemporaryFile(suffix=f"_{file.filename}", delete=True) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp.flush()
            transcript_text = await transcribe_file(tmp.name)
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

        # Store audit task (skip for create_project — the project IS the artifact)
        logged_task_id = None
        if intent_type != "create_project":
            fresh_projects = models.get_user_projects(user.id)
            logged_task_id = models.log_agent_event_task(
                user_id=user.id,
                project_name=project_name,
                projects=fresh_projects,
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

# --- 5b. TEXT COMMAND (dev mode — skips Whisper) ---

class TextCommandRequest(BaseModel):
    text: str

@app.post("/transcribe-text")
async def transcribe_text(
    request: TextCommandRequest,
    user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
):
    """Same pipeline as /transcribe but accepts text directly (skips Whisper STT)."""
    try:
        transcript_text = request.text.strip()
        if not transcript_text:
            return {"status": "error", "message": "Empty text"}

        models.upsert_user(
            user_id=user.id,
            email=getattr(user, "email", None) or f"{user.id}@local",
            phone_number=getattr(user, "phone", None),
        )

        user_projects = models.get_user_projects(user.id)
        intent_data = await parse_intent(transcript_text, user_projects) or {"intent": "unknown"}

        intent_type = intent_data.get("intent") or "unknown"
        project_name = intent_data.get("project_name")
        task_description = intent_data.get("task_description")

        action_result = None
        created = {"project_id": None, "task_id": None}

        if intent_type == "create_project":
            if project_name:
                created["project_id"] = models.create_project(user.id, project_name)
                action_result = f"Successfully created project '{project_name}'."
            else:
                action_result = "I couldn't determine a project name."
        elif intent_type == "create_task":
            if project_name and task_description:
                project = models.get_project_by_name(user.id, project_name)
                if project:
                    models.touch_project(project["id"])
                    created["task_id"] = models.create_task(
                        project_id=project["id"], user_id=user.id,
                        description=task_description, voice_command=transcript_text,
                        raw_transcript=transcript_text, intent_type=intent_type,
                    )
                    action_result = f"Created task '{task_description}' in project '{project_name}'."
                else:
                    action_result = f"Could not find a project named '{project_name}'."
            else:
                action_result = "I couldn't determine the project or task from your command."
        elif intent_type == "status_check":
            projects_with_counts = models.get_user_projects_with_task_counts(user.id)
            if not projects_with_counts:
                action_result = "You don't have any projects yet."
            else:
                lines = [f"You have {len(projects_with_counts)} project(s):"]
                for p in projects_with_counts:
                    lines.append(f"  '{p['name']}' — {p['total_tasks'] or 0} task(s)")
                action_result = "\n".join(lines)
        else:
            action_result = "I wasn't able to map that command to an action."

        # Skip audit log for create_project (the project IS the artifact)
        logged_task_id = None
        if intent_type != "create_project":
            fresh_projects = models.get_user_projects(user.id)
            logged_task_id = models.log_agent_event_task(
                user_id=user.id, project_name=project_name, projects=fresh_projects,
                description=task_description or f"[{intent_type}] {transcript_text}",
                raw_transcript=transcript_text, intent_type=intent_type,
                intent_confidence=None, output_summary=action_result, voice_command=transcript_text,
            )

        dispatch_task_id = created.get("task_id") or logged_task_id
        agent_status = None
        terminal_granted = get_terminal_access(user.id)
        if intent_type in ("create_task", "create_project", "fix_bug") and dispatch_task_id:
            if background_tasks:
                background_tasks.add_task(agent_dispatch_task, dispatch_task_id, intent_data, terminal_granted)
                agent_status = "dispatching"

        return {
            "status": "success",
            "transcript": transcript_text,
            "intent": intent_data,
            "action_result": action_result,
            "context_projects_count": len(models.get_user_projects(user.id)),
            "created": created,
            "logged_task_id": logged_task_id,
            "agent_status": agent_status,
            "terminal_access": terminal_granted,
        }
    except Exception as e:
        import traceback
        logger.error("transcribe-text pipeline error=%r trace=%s", e, traceback.format_exc())
        return {"status": "error", "message": "Internal server error"}

# --- 6. CRUD ENDPOINTS (For Dashboard) ---

@app.get("/api/dashboard/{user_id}")
async def get_dashboard(user_id: str, user: dict = Depends(get_current_user)):
    _require_user_match(user_id, user.id)
    projects = models.get_user_projects_with_task_counts(user_id)
    tasks = models.get_user_tasks(user_id)
    logger.debug("dashboard user_id=%s projects=%s tasks=%s", user_id, len(projects), len(tasks))
    return {
        "success": True,
        "projects": projects,
        "tasks": tasks,
    }

@app.get("/api/projects/{user_id}")
async def get_user_projects(user_id: str, user: dict = Depends(get_current_user)):
    _require_user_match(user_id, user.id)
    return {"success": True, "projects": models.get_user_projects(user_id)}

@app.post("/api/projects")
async def create_project(request: CreateProjectRequest, user: dict = Depends(get_current_user)):
    _require_user_match(request.user_id, user.id)
    models.upsert_user(user_id=user.id, email=getattr(user, "email", None) or f"{user.id}@local", phone_number=getattr(user, "phone", None))
    pid = models.create_project(user.id, request.name, request.file_path)
    return {"success": True, "project_id": pid}

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, user: dict = Depends(get_current_user)):
    _require_project_owner(user.id, project_id)
    models.delete_project(project_id)
    return {"success": True}

@app.get("/api/projects/{project_id}/tasks")
async def get_project_tasks(project_id: str, user: dict = Depends(get_current_user)):
    _require_project_owner(user.id, project_id)
    return {"success": True, "tasks": models.get_project_tasks(project_id)}

@app.post("/api/tasks")
async def create_task(request: CreateTaskRequest, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    _require_user_match(request.user_id, user.id)
    _require_project_owner(user.id, request.project_id)
    tid = models.create_task(request.project_id, request.user_id, request.description)

    # Auto-dispatch if terminal access is granted
    terminal_granted = get_terminal_access(request.user_id)
    if terminal_granted:
        intent_data = {
            "intent": "create_task",
            "task_description": request.description,
        }
        background_tasks.add_task(agent_dispatch_task, tid, intent_data, terminal_granted)

    return {"success": True, "task_id": tid}

@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: str, request: UpdateTaskRequest, user: dict = Depends(get_current_user)):
    _require_task_owner(user.id, task_id)
    models.update_task_status(task_id, request.status)
    return {"success": True, "message": "Task updated"}

@app.get("/api/call-sessions/{user_id}")
async def get_call_history(user_id: str, user: dict = Depends(get_current_user)):
    _require_user_match(user_id, user.id)
    sessions = models.get_user_call_history(user_id, limit=20)
    return {"success": True, "sessions": sessions}

# --- 7. AGENT PIPELINE ENDPOINTS ---

@app.get("/api/agent/status/{task_id}")
async def get_agent_status(task_id: str, user: dict = Depends(get_current_user)):
    """Get agent pipeline status for a specific task."""
    _require_task_owner(user.id, task_id)
    executions = models.get_agent_executions(task_id)
    latest = models.get_task_agent_status(task_id)
    return {
        "success": True,
        "task_id": task_id,
        "latest": latest,
        "executions": executions,
    }


@app.get("/api/agent/executions/{user_id}")
async def get_user_agent_executions(user_id: str, user: dict = Depends(get_current_user)):
    """Get all agent executions for a user."""
    _require_user_match(user_id, user.id)
    executions = models.get_user_agent_executions(user_id)
    return {
        "success": True,
        "executions": executions,
    }


@app.post("/api/agent/dispatch/{task_id}")
async def manually_dispatch_agent(task_id: str, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    """Manually trigger agent dispatch for a task."""
    task_dict = _require_task_owner(user.id, task_id)
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
async def grant_terminal_access(user_id: str, user: dict = Depends(get_current_user)):
    """User grants permission for auto-terminal execution."""
    _require_user_match(user_id, user.id)
    set_terminal_access(user_id, True)
    return {"success": True, "terminal_access": True, "message": "Terminal access granted. Tasks will auto-execute in terminal."}


@app.delete("/api/agent/terminal-access/{user_id}")
async def revoke_terminal_access(user_id: str, user: dict = Depends(get_current_user)):
    """User revokes terminal execution permission."""
    _require_user_match(user_id, user.id)
    set_terminal_access(user_id, False)
    return {"success": True, "terminal_access": False, "message": "Terminal access revoked."}


@app.get("/api/agent/terminal-access/{user_id}")
async def check_terminal_access(user_id: str, user: dict = Depends(get_current_user)):
    """Check if user has granted terminal access."""
    _require_user_match(user_id, user.id)
    granted = get_terminal_access(user_id)
    return {"success": True, "terminal_access": granted}


@app.post("/api/device/heartbeat")
async def device_heartbeat(
    request: DeviceHeartbeatRequest,
    device: dict = Depends(get_current_device),
):
    if request.device_id != device.get("id"):
        raise HTTPException(status_code=403, detail="Forbidden")
    models.touch_device_heartbeat(device["id"])
    return {"success": True, "device_id": device["id"]}


@app.post("/api/device/claim-next")
async def device_claim_next(
    request: DeviceClaimRequest,
    device: dict = Depends(get_current_device),
):
    wait_s = max(0, min(request.wait_seconds, 30))
    try:
        cmd = models.claim_next_queued_command_for_device(device_id=device["id"])
    except Exception as exc:
        logger.warning("device claim-next error device_id=%s err=%r", device["id"], exc)
        cmd = None
    if not cmd and wait_s > 0:
        deadline = asyncio.get_running_loop().time() + wait_s
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.5)
            try:
                cmd = models.claim_next_queued_command_for_device(device_id=device["id"])
            except Exception:
                cmd = None
            if cmd:
                break
    return {"success": True, "command": cmd}


@app.post("/api/device/commands/{command_id}/append-logs")
async def device_append_logs(
    command_id: str,
    request: AppendTerminalLogsRequest,
    device: dict = Depends(get_current_device),
):
    cmd = _require_terminal_command_owner(device["user_id"], command_id)
    seq = request.sequence_start
    for chunk in request.chunks:
        models.append_terminal_log_chunk(command_id=command_id, sequence=seq, stream=request.stream, chunk=chunk)
        seq += 1
    models.touch_device_heartbeat(device["id"])
    return {"success": True, "command_id": cmd["id"], "next_sequence": seq}


@app.post("/api/device/commands/{command_id}/complete")
async def device_complete_command(
    command_id: str,
    request: CompleteTerminalCommandRequest,
    device: dict = Depends(get_current_device),
):
    _require_terminal_command_owner(device["user_id"], command_id)
    if request.status not in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status")
    models.complete_terminal_command(command_id=command_id, status=request.status, exit_code=request.exit_code)
    models.touch_device_heartbeat(device["id"])
    return {"success": True}


@app.post("/api/device/cursor-context")
async def upsert_cursor_context(
    request: CursorContextRequest,
    device: dict = Depends(get_current_device),
):
    _require_project_owner(device["user_id"], request.project_id)
    linked_projects = {row.get("project_id") for row in models.get_device_project_links(device["id"])}
    if request.project_id not in linked_projects:
        raise HTTPException(status_code=403, detail="Device is not linked to this project")
    context_id = models.save_cursor_context(
        device_id=device["id"],
        project_id=request.project_id,
        file_path=request.file_path,
        selection=request.selection,
        diagnostics=request.diagnostics,
    )
    models.touch_device_heartbeat(device["id"])
    return {"success": True, "context_id": context_id}


@app.post("/api/unified/commands")
async def create_unified_command(
    request: UnifiedCommandRequest,
    user: dict = Depends(get_current_user),
):
    _require_project_owner(user.id, request.project_id)
    from agents.command_builder import build_provider_command, normalize_provider

    provider = normalize_provider(request.provider or models.get_default_provider_for_user(user.id))
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    if request.device_id:
        _require_device_owner(user.id, request.device_id)
        context = models.get_latest_cursor_context(device_id=request.device_id, project_id=request.project_id)
        if context:
            file_path = context.get("file_path") or "(unknown file)"
            selection = (context.get("selection") or "").strip()
            diagnostics = (context.get("diagnostics") or "").strip()
            prompt = (
                f"{prompt}\n\n"
                f"CursorContext file={file_path}\n"
                f"Selection:\n{selection or '(none)'}\n"
                f"Diagnostics:\n{diagnostics or '(none)'}"
            )

    session = models.get_or_create_terminal_session_for_project(
        user_id=user.id,
        project_id=request.project_id,
        name=request.session_name or "Unified Session",
    )
    command = build_provider_command(provider=provider, prompt=prompt)
    command_id = models.create_terminal_command(
        session_id=session["id"],
        user_id=user.id,
        command=command,
        source=request.source,
        provider=provider,
        user_prompt=prompt,
        normalized_command=command,
    )
    logger.info(
        "unified command queued user_id=%s project_id=%s session_id=%s provider=%s source=%s command_id=%s",
        user.id,
        request.project_id,
        session["id"],
        provider,
        request.source,
        command_id,
    )
    return {
        "success": True,
        "session_id": session["id"],
        "command_id": command_id,
        "provider": provider,
        "normalized_command": command,
    }


@app.get("/api/unified/timeline")
async def get_unified_timeline(
    project_id: str | None = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    safe_limit = max(1, min(limit, 200))
    rows = models.list_recent_terminal_commands_for_user(user_id=user.id, limit=safe_limit)
    if project_id:
        rows = [r for r in rows if r.get("project_id") == project_id]
    return {"success": True, "commands": rows}


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
    elif request.project_path is not None:
        # Create (or reuse) project automatically for minimal user friction
        inferred_name = (request.project_name or "").strip()
        if not inferred_name:
            inferred_name = os.path.basename(request.project_path.rstrip("/")) or "Local Project"
        project = models.upsert_project_by_name(
            user_id=agent_user_id,
            name=inferred_name,
            file_path=request.project_path,
        )
        project_id = project["id"]
    # else: neither project_id nor project_path provided — register as project-agnostic instance

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
    inst = models.get_instance_by_id(request.instance_id)
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
    inst = models.get_instance_by_id(request.instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    if inst.get("user_id") and inst["user_id"] != agent_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    wait_s = max(0, min(request.wait_seconds, 30))
    cmd = models.claim_next_queued_command_for_user(user_id=agent_user_id)
    if not cmd and wait_s > 0:
        deadline = asyncio.get_running_loop().time() + wait_s
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.5)
            cmd = models.claim_next_queued_command_for_user(user_id=agent_user_id)
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
        active = models.get_active_instances_for_user(user.id, within_seconds=120)
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
        # Try to auto-bind to latest active instance for this user.
        active = models.get_active_instances_for_user(user.id, within_seconds=180)
        if active:
            models.bind_terminal_session_instance(session_id, active[0]["id"])
            session = _require_terminal_session_owner(user.id, session_id)
        if not session.get("instance_id"):
            raise HTTPException(status_code=409, detail="No local agent connected for this session")
    provider = (request.provider or models.get_default_provider_for_user(user.id)).strip().lower()
    command_id = models.create_terminal_command(
        session_id=session_id,
        user_id=user.id,
        command=request.command,
        source="typed",
        provider=provider,
        user_prompt=request.command,
        normalized_command=request.command,
    )
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
    return {"status": "Dispatch Agent is Listening..."}

@app.post("/twilio/incoming")
async def twilio_incoming(request: Request):
    """
    Twilio calls this webhook when someone calls the Twilio number.
    It records the caller's voice and sends it to our transcription pipeline.
    """
    from twilio.twiml.voice_response import VoiceResponse, Record
    
    response = VoiceResponse()
    response.say("Welcome to Dispatch. Please say your command after the beep.")
    response.record(
        action="/twilio/recording",
        method="POST",
        max_length=30,
        transcribe=False,
        play_beep=True,
    )
    return Response(content=str(response), media_type="application/xml")


@app.post("/twilio/recording")
async def twilio_recording(request: Request, background_tasks: BackgroundTasks):
    """
    Twilio calls this after the recording is done.
    Downloads the audio, transcribes, parses intent, and dispatches to agent pipeline.
    """
    import httpx
    import tempfile
    from twilio.twiml.voice_response import VoiceResponse

    form = await request.form()
    recording_url = form.get("RecordingUrl")
    caller_number = form.get("From", "")

    response = VoiceResponse()

    if not recording_url:
        response.say("Sorry, I could not process your command.")
        return Response(content=str(response), media_type="application/xml")

    try:
        # Download the audio from Twilio
        async with httpx.AsyncClient() as client:
            audio_response = await client.get(
                f"{recording_url}.mp3",
                auth=(os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN")),
            )

        # Transcribe via Groq Whisper API
        audio_bytes = audio_response.content
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            transcript = await transcribe_file(tmp.name)

        # Look up user by phone number
        user_id = models.get_user_id_by_phone(caller_number)
        if not user_id:
            logger.warning("twilio recording from unknown number=%s", caller_number)
            intent_data = await parse_intent(transcript, []) or {"intent": "unknown"}
            response.say(f"I heard: {transcript}. But I could not find your account.")
            return Response(content=str(response), media_type="application/xml")

        # Save call session
        call_session_id = models.create_call_session(user_id, caller_number)
        user_projects = models.get_user_projects(user_id)
        intent_data = await parse_intent(transcript, user_projects) or {"intent": "unknown"}
        models.update_call_session(call_session_id, transcript, str(intent_data))

        intent_type = intent_data.get("intent", "unknown")
        task_description = intent_data.get("task_description") or transcript
        project_name = intent_data.get("project_name")

        # Create a task from the voice command
        logged_task_id = None
        if intent_type != "unknown":
            logged_task_id = models.log_agent_event_task(
                user_id=user_id,
                project_name=project_name,
                projects=user_projects,
                description=task_description,
                raw_transcript=transcript,
                intent_type=intent_type,
                intent_confidence=None,
                output_summary=None,
                voice_command=transcript,
            )

        # Dispatch to agent pipeline if actionable
        if intent_type in ("create_task", "create_project", "fix_bug") and logged_task_id:
            terminal_granted = get_terminal_access(user_id)
            background_tasks.add_task(agent_dispatch_task, logged_task_id, intent_data, terminal_granted)
            logger.info(
                "twilio dispatch queued task_id=%s user=%s terminal=%s",
                logged_task_id, user_id, terminal_granted,
            )
            response.say(f"I heard: {transcript}. Your command is being dispatched now.")
        else:
            response.say(f"I heard: {transcript}. I've recorded your request.")

    except Exception as e:
        logger.error("twilio recording error=%r", e)
        response.say("Sorry, something went wrong processing your command.")

    return Response(content=str(response), media_type="application/xml")
