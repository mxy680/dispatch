# server/services/llm.py
import json
import os
from openai import AsyncOpenAI

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-3-haiku")

if not OPENROUTER_API_KEY:
    print("[LLM] WARNING: OPENROUTER_API_KEY not set. Intent parsing will fail.")

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

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
    project_names = [p['name'] for p in projects]
    context_str = f"Available Projects: {', '.join(project_names)}"

    user_message = f"""
    Context: {context_str}
    User Command: "{text}"
    """

    try:
        response = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1024,
        )

        content_text = response.choices[0].message.content

        # Clean up if the model adds markdown code blocks
        if "```json" in content_text:
            content_text = content_text.split("```json")[1].split("```")[0].strip()
        elif "```" in content_text:
            content_text = content_text.split("```")[1].split("```")[0].strip()

        return json.loads(content_text)

    except Exception as e:
        print(f"[LLM] OpenRouter error: {e}")
        return {"intent": "error", "message": str(e)}
