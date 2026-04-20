from __future__ import annotations

# server/services/llm.py
"""Intent parsing via Groq LLM API."""

import json
import logging
import os

from typing import Optional
from openai import AsyncOpenAI

logger = logging.getLogger("dispatch.llm")

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        _client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )
    return _client


SYSTEM_PROMPT = """
You are the "Brain" of a voice coding assistant. Map natural language to tools.
Output STRICT JSON only. No markdown, no conversational text.

Structure:
{
  "intent": "create_project" | "create_task" | "fix_bug" | "status_check" | "unknown",
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

    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1024,
            response_format={"type": "json_object"},
        )

        content_text = response.choices[0].message.content

        # Clean up if the model adds markdown code blocks
        if "```json" in content_text:
            content_text = content_text.split("```json")[1].split("```")[0].strip()
        elif "```" in content_text:
            content_text = content_text.split("```")[1].split("```")[0].strip()

        return json.loads(content_text)

    except Exception as e:
        logger.error("Groq intent parsing error: %r", e)
        return {"intent": "error", "message": str(e)}
