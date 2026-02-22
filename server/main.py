import os
import shutil
from typing import Annotated, Union
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel
from supabase import create_client, Client
from pydantic import BaseModel

DEVELOPMENT_MODE = os.environ.get("DEVELOPMENT_MODE", "true").lower() == "true"

# --- LOCAL IMPORTS ---
# Make sure these files exist from the previous step!
from database.connection import init_database
from database import models
from services.llm import parse_intent

app = FastAPI(title="CallStack API")

# --- CONFIG ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

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
    """

        # BYPASS AUTH IN DEVELOPMENT
    if DEVELOPMENT_MODE:
        class MockUser:
            id = "test-user-123"
            email = "test@example.com"
            phone = "+15551234567"
        return MockUser()


    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    
    try:
        if " " in authorization:
            token = authorization.split(" ")[1]
        else:
            token = authorization
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        user_response = supabase.auth.get_user(token)
        return user_response.user
    except Exception as e:
        print(f"Auth Error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or Expired Token")

# --- 4. REQUEST MODELS ---
class CreateProjectRequest(BaseModel):
    user_id: str
    name: str
    file_path: str = None

class CreateTaskRequest(BaseModel):
    project_id: str
    description: str

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
        # A. Transcribe
        temp_filename = f"temp_{file.filename}"
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        segments, info = model.transcribe(temp_filename, beam_size=5)
        transcript_text = " ".join([segment.text for segment in segments]).strip()
        os.remove(temp_filename)
        
        # B. Get Context (The Memory)
        # We need the user's existing projects so the LLM knows what they are talking about
        user_projects = models.get_user_projects(user.id)
        
        # C. Parse Intent (The Brain)
        intent_data = await parse_intent(transcript_text, user_projects)
        
        # D. Execute Action (The Hands)
        action_result = None
        
        # --- HANDLER: CREATE PROJECT ---
        if intent_data.get("intent") == "create_project":
            new_project_name = intent_data.get("project_name")
            if new_project_name:
                project_id = models.create_project(user.id, new_project_name)
                action_result = f"Successfully created project '{new_project_name}'."
        
        # --- HANDLER: CREATE TASK ---
        elif intent_data.get("intent") == "create_task":
            project_name = intent_data.get("project_name")
            task_description = intent_data.get("task_description")
            if project_name and task_description:
                project = models.get_project_by_name(user.id, project_name)
                if project:
                    models.create_task(project["id"], task_description, voice_command=transcript_text)
                    action_result = f"Created task '{task_description}' in project '{project_name}'."
                else:
                    action_result = f"Could not find a project named '{project_name}'."
            else:
                action_result = "I couldn't determine the project or task from your command."

        # --- HANDLER: STATUS CHECK ---
        elif intent_data.get("intent") == "status_check":
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

        return {
            "status": "success",
            "transcript": transcript_text,
            "intent": intent_data,
            "action_result": action_result,
            "context_projects_count": len(user_projects)
        }

    except Exception as e:
        print(f"Pipeline Error: {e}")
        return {"status": "error", "message": str(e)}

# --- 6. CRUD ENDPOINTS (For Dashboard) ---

@app.get("/api/projects/{user_id}")
async def get_user_projects(user_id: str):
    return {"success": True, "projects": models.get_user_projects(user_id)}

@app.post("/api/projects")
async def create_project(request: CreateProjectRequest):
    pid = models.create_project(request.user_id, request.name, request.file_path)
    return {"success": True, "project_id": pid}

@app.get("/api/projects/{project_id}/tasks")
async def get_project_tasks(project_id: str):
    return {"success": True, "tasks": models.get_project_tasks(project_id)}

@app.post("/api/tasks")
async def create_task(request: CreateTaskRequest):
    tid = models.create_task(request.project_id, request.description)
    return {"success": True, "task_id": tid}

@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: str, request: UpdateTaskRequest):
    models.update_task_status(task_id, request.status)
    return {"success": True, "message": "Task updated"}

@app.get("/")
async def root():
    return {"status": "CallStack Agent is Listening..."}

@app.get("/health")
async def health():
    return {"status": "healthy"}