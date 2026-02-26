import os
import shutil
import json
from typing import Annotated, Union
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel
from supabase import create_client, Client
from pydantic import BaseModel

# NEW: load server/.env when running locally (uvicorn doesn't auto-load it)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception as e:
    print(f"[ENV] python-dotenv not available or failed to load: {e!r}")

DEVELOPMENT_MODE = os.environ.get("DEVELOPMENT_MODE", "true").lower() == "true"

# --- DEBUG: Print all environment variables ---
print("[ENV DEBUG] All environment variables:")
for key, value in os.environ.items():
    if "SUPABASE" in key or "NEXT_PUBLIC" in key:
        # Mask sensitive values
        masked_value = value[:10] + "..." if len(value) > 10 else value
        print(f"[ENV DEBUG] {key}={masked_value}")

# --- LOCAL IMPORTS ---
from database.connection import init_database
from database import models
from services.llm import parse_intent

app = FastAPI(title="CallStack API")

# --- CONFIG ---
SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")

print(f"[ENV] DEVELOPMENT_MODE={DEVELOPMENT_MODE}")
print(f"[ENV] SUPABASE_URL={SUPABASE_URL[:30] + '...' if SUPABASE_URL else None}")
print(f"[ENV] SUPABASE_SERVICE_KEY={'SET' if SUPABASE_SERVICE_KEY else 'NOT SET'}")
print(f"[ENV] SUPABASE_URL_set={bool(SUPABASE_URL)} SUPABASE_SERVICE_KEY_set={bool(SUPABASE_SERVICE_KEY)}")
print(f"[ENV] DEVELOPMENT_MODE={DEVELOPMENT_MODE} SUPABASE_URL_set={bool(SUPABASE_URL)} SUPABASE_SERVICE_KEY_set={bool(SUPABASE_SERVICE_KEY)}")

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
print("Loading Whisper model... this might take a moment...")
model = WhisperModel("tiny", device="cpu", compute_type="int8")
print("Whisper model loaded!")

# --- 3. SECURITY ---
def get_current_user(authorization: Annotated[Union[str, None], Header()] = None):
    """
    Validates the Supabase JWT. Returns the Supabase User object.
    In DEVELOPMENT_MODE: if a JWT is provided, use it; otherwise fall back to a mock user.
    """
    # If a real token is present, always honor it (even in dev mode)
    has_auth = bool(authorization)
    print(f"[AUTH] DEVELOPMENT_MODE={DEVELOPMENT_MODE} has_auth={has_auth}")

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
            print(f"[AUTH] Using Supabase user id={getattr(u, 'id', None)} email={getattr(u, 'email', None)}")
            return u
        except Exception as e:
            print(f"[AUTH] Supabase auth failed err={e!r}")
            raise HTTPException(status_code=401, detail="Invalid or Expired Token")

    # No token (or token invalid in dev): allow mock user only in dev mode
    if DEVELOPMENT_MODE:
        class MockUser:
            id = os.environ.get("DEV_USER_ID", "test-user-123")
            email = os.environ.get("DEV_USER_EMAIL", "test@example.com")
            phone = os.environ.get("DEV_USER_PHONE", "+15551234567")
        mu = MockUser()
        print(f"[AUTH] Falling back to MockUser id={mu.id} email={mu.email}")
        return mu

    raise HTTPException(status_code=401, detail="Missing Authorization Header")

# --- 4. REQUEST MODELS ---
class CreateProjectRequest(BaseModel):
    user_id: str
    name: str
    file_path: str = None

class CreateTaskRequest(BaseModel):
    project_id: str
    description: str
    # allow client/dashboard-created tasks to attach user_id explicitly
    user_id: str | None = None

class UpdateTaskRequest(BaseModel):
    status: str

# --- 5. THE CORE ENDPOINT (EAR + BRAIN + HANDS) ---
@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...), 
    user: dict = Depends(get_current_user)
):
    """
    1. Transcribes Audio (Whisper)
    2. Fetches Context (SQLite)
    3. Determines Intent (Bedrock)
    4. Executes Action (SQLite)
    """
    try:
        print(f"[TRANSCRIBE] start user_id={getattr(user, 'id', None)} filename={file.filename}")

        # Ensure a corresponding users row exists (id comes from Supabase)
        models.upsert_user(
            user_id=user.id,
            email=getattr(user, "email", None) or f"{user.id}@local",
            phone_number=getattr(user, "phone", None),
        )

        # A. Transcribe
        print(f"[TRANSCRIBE] Step A: Starting audio transcription")
        temp_filename = f"temp_{file.filename}"
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        segments, info = model.transcribe(temp_filename, beam_size=5)
        transcript_text = " ".join([segment.text for segment in segments]).strip()
        os.remove(temp_filename)
        print(f"[TRANSCRIBE] transcript='{transcript_text}'")
        
        # B. Context
        print(f"[TRANSCRIBE] Step B: Fetching user projects")
        user_projects = models.get_user_projects(user.id)
        print(f"[TRANSCRIBE] context_projects_count={len(user_projects)} names={[p.get('name') for p in user_projects]}")
        # C. Parse Intent
        print(f"[TRANSCRIBE] Step C: Parsing intent with LLM")
        intent_data = await parse_intent(transcript_text, user_projects) or {"intent": "unknown"}
        print(f"[TRANSCRIBE] raw_intent_data={json.dumps(intent_data, ensure_ascii=False)}")
        
        # Normalize for storage
        intent_type = intent_data.get("intent") or "unknown"
        project_name = intent_data.get("project_name")
        task_description = intent_data.get("task_description")
        print(f"[TRANSCRIBE] normalized intent_type={intent_type} project_name={project_name!r} task_description={task_description!r}")

        action_result = None
        created = {"project_id": None, "task_id": None}
        
        # --- HANDLER: CREATE PROJECT ---
        if intent_type == "create_project":
            new_project_name = project_name
            if new_project_name:
                created["project_id"] = models.create_project(user.id, new_project_name)
                action_result = f"Successfully created project '{new_project_name}'."
                print(f"[TRANSCRIBE] create_project created_project_id={created['project_id']}")
            else:
                action_result = "I couldn't determine a project name."
        
        # --- HANDLER: CREATE TASK ---
        elif intent_type == "create_task":
            if project_name and task_description:
                project = models.get_project_by_name(user.id, project_name)
                print(f"[TRANSCRIBE] lookup_project_by_name user_id={user.id} project_name={project_name!r} found={bool(project)}")
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
                    print(f"[TRANSCRIBE] create_task created_task_id={created['task_id']} project_id={project['id']}")
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
            print("[TRANSCRIBE] status_check executed")

        else:
            action_result = "I wasn't able to map that command to an action."
            print("[TRANSCRIBE] unknown intent executed")

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
        print(f"[TRANSCRIBE] log_agent_event_task wrote task_id={logged_task_id} user_id={user.id}")

        return {
            "status": "success",
            "transcript": transcript_text,
            "intent": intent_data,
            "action_result": action_result,
            "context_projects_count": len(user_projects),
            "created": created,
            "logged_task_id": logged_task_id,
        }

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[TRANSCRIBE] Pipeline Error: {e!r}")
        print(f"[TRANSCRIBE] Full traceback:\n{error_trace}")
        return {"status": "error", "message": str(e), "traceback": error_trace}

# --- 6. CRUD ENDPOINTS (For Dashboard) ---

@app.get("/api/dashboard/{user_id}")
async def get_dashboard(user_id: str):
    projects = models.get_user_projects_with_task_counts(user_id)
    tasks = models.get_user_tasks(user_id)
    print(f"[DASHBOARD] user_id={user_id} projects={len(projects)} tasks={len(tasks)}")
    if tasks:
        print(f"[DASHBOARD] sample_task_ids={[t.get('id') for t in tasks[:3]]}")
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

@app.get("/")
async def root():
    return {"status": "CallStack Agent is Listening..."}

@app.get("/health")
async def health():
    return {"status": "healthy"}
