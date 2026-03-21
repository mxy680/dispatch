# server/services/llm.py
import boto3
import json
import os

from groq import AsyncGroq

client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL_ID = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """
You are the "Brain" of a voice coding assistant. Map natural language to tools.
Output STRICT JSON only. No markdown, no conversational text.

Structure:
{
  "intent": "create_project" | "create_task" | "status_check" | "unknown",
  "project_name": <string | null>,
  "task_description": <string | null>,
  "parameters": <object>
}
"""

async def parse_intent(text: str, projects: list):
    # Format project context
    project_names = [p['name'] for p in projects]
    context_str = f"Available Projects: {', '.join(project_names)}"
    
    user_message = f"""
    Context: {context_str}
    User Command: "{text}"
    """

    try:
        chat_completion = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            model=MODEL_ID,
            response_format={"type": "json_object"} # Forces JSON output
        )
        return json.loads(chat_completion.choices[0].message.content)
    except Exception as e:
        print(f"Groq Error: {e}")
        return {"intent": "error", "message": str(e)}