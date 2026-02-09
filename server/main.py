# server/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
from typing import Annotated
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel
from supabase import create_client, Client


app = FastAPI(title="CallStack API")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "ok", "service": "callstack-api"}


@app.get("/health")
async def health():
    return {"status": "healthy"}

# --- 1. Global State (Model Loading) ---
# "tiny" is fast and decent. Use "base" or "small" for better accuracy.
# device="cpu" or "cuda" (if you have NVIDIA). On Mac M1/M2, "cpu" with verify is fine, 
# or look into "mps" support if available in your version.
print("Loading Whisper model... this might take a moment...")
model = WhisperModel("tiny", device="cpu", compute_type="int8")
print("Whisper model loaded!")

# --- 2. Security Dependency ---
def get_current_user(authorization: Annotated[str | None, Header()] = None):
    """
    Validates the Supabase JWT sent in the 'Authorization' header.
    Returns the user object if valid, raises 401 if not.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    
    try:
        # Extract the token (Remove "Bearer " prefix)
        token = authorization.split(" ")[1]
        
        # Initialize Supabase Client (Lazy initialization is fine here)
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        
        # Verify the token by asking Supabase "Who is this?"
        user_response = supabase.auth.get_user(token)
        return user_response.user

    except Exception as e:
        print(f"Auth Error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or Expired Token")

# --- 3. The Endpoint ---
@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...), 
    user: dict = Depends(get_current_user) # Locks this route!
):


    
    """
    Accepts an audio file, transcribes it locally, and returns the text.
    """
    try:
        # 1. Save the upload to a temporary file (Whisper needs a file path)
        temp_filename = f"temp_{file.filename}"
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. Run Transcription
        # beam_size=5 is standard for good accuracy
        segments, info = model.transcribe(temp_filename, beam_size=5)
        
        # 3. Combine segments into one string
        transcript_text = " ".join([segment.text for segment in segments]).strip()
        
        # 4. Clean up temp file
        os.remove(temp_filename)
        
        return {
            "status": "success",
            "language": info.language,
            "probability": info.language_probability,
            "transcript": transcript_text,
            "user_id": user.id # Proof that we know who sent it!
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/")
async def root():
    return {"status": "CallStack Agent is Listening..."}