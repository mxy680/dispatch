# server/services/security_analyzer.py
"""Async LLM-based risk classification for terminal / agent commands (Groq)."""

from __future__ import annotations

import json
import logging
import os
import re

from openai import AsyncOpenAI

logger = logging.getLogger("dispatch.security")

_client: AsyncOpenAI | None = None

VALID_LEVELS = frozenset({"SAFE", "WARNING", "HIGH_RISK"})

SYSTEM = """You are a security analyzer for a local terminal / coding agent.
Analyze the proposed command and classify operational risk to the user's machine and data.

Respond with STRICT JSON only (no markdown):
{"risk_level":"SAFE"|"WARNING"|"HIGH_RISK","risk_reason":"<one short sentence>"}

Rules:
- HIGH_RISK: destructive filesystem (e.g. rm -rf), privilege escalation, credential exfil, piping secrets, curl|bash from unknown URLs, chmod 777 on sensitive paths, disk wipe patterns.
- WARNING: network calls, package installs, git force operations, broad find/delete, environment variable dumps that might leak secrets.
- SAFE: read-only listing, grep, cat of non-secret files, benign git status, simple builds in a project.

If unsure, prefer WARNING over SAFE."""


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


def _parse_json_object(raw: str) -> dict:
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    return json.loads(text)


def _normalize_level(level: str) -> str:
    u = (level or "").strip().upper().replace(" ", "_")
    if u == "HIGHRISK":
        u = "HIGH_RISK"
    if u in VALID_LEVELS:
        return u
    return "WARNING"


async def analyze_command_security(
    *,
    user_prompt: str | None,
    normalized_command: str | None,
) -> dict[str, str]:
    """
    Returns {"risk_level": "SAFE"|"WARNING"|"HIGH_RISK", "risk_reason": str}.
    """
    cmd = (normalized_command or "").strip() or "(empty)"
    prompt_ctx = (user_prompt or "").strip()[:4000]
    user_message = f"User request context (may be truncated):\n{prompt_ctx}\n\nNormalized command:\n{cmd}\n"

    model = os.environ.get("GROQ_SECURITY_MODEL") or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    client = _get_client()
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_message},
        ],
        max_tokens=256,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    content_text = response.choices[0].message.content or "{}"
    data = _parse_json_object(content_text)
    level = _normalize_level(str(data.get("risk_level", "WARNING")))
    reason = str(data.get("risk_reason", "") or "").strip()
    if not reason:
        reason = "Automated risk assessment completed."
    if len(reason) > 500:
        reason = reason[:497] + "..."
    return {"risk_level": level, "risk_reason": reason}


async def analyze_command_security_heuristic_fallback(
    *,
    user_prompt: str | None,
    normalized_command: str | None,
) -> dict[str, str]:
    """
    Used when GROQ_API_KEY is missing or the LLM call fails.
    """
    text = f"{user_prompt or ''}\n{normalized_command or ''}".lower()
    high_patterns = [
        r"rm\s+-rf",
        r"mkfs\.",
        r"dd\s+if=",
        r">\s*/dev/",
        r"curl\s+[^|]+\s*\|\s*(ba)?sh",
        r"wget\s+[^|]+\s*\|\s*(ba)?sh",
        r"chmod\s+[-+]?\s*777",
    ]
    for pat in high_patterns:
        if re.search(pat, text):
            return {
                "risk_level": "HIGH_RISK",
                "risk_reason": "Pattern matches a potentially destructive or high-risk shell operation.",
            }
    warn_patterns = [
        r"\bcurl\b",
        r"\bwget\b",
        r"\bnpm\s+install\b",
        r"\bpip\s+install\b",
        r"\bgit\s+push\b",
        r"\bgit\s+reset\s+--hard\b",
    ]
    for pat in warn_patterns:
        if re.search(pat, text):
            return {
                "risk_level": "WARNING",
                "risk_reason": "Command may perform network or repo changes; review before running.",
            }
    return {"risk_level": "SAFE", "risk_reason": "No obvious high-risk patterns detected (heuristic scan only)."}


async def analyze_command_security_with_fallback(
    *,
    user_prompt: str | None,
    normalized_command: str | None,
) -> dict[str, str]:
    try:
        return await analyze_command_security(
            user_prompt=user_prompt,
            normalized_command=normalized_command,
        )
    except Exception as e:
        logger.warning("LLM security analyzer failed, using heuristic: %r", e)
        return await analyze_command_security_heuristic_fallback(
            user_prompt=user_prompt,
            normalized_command=normalized_command,
        )
