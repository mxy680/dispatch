"""
Build provider-specific CLI commands from a user prompt.

Supported providers:
  - cursor  → `cursor --cli agent -p "<prompt>" --output-format text`
  - claude  → `claude -p "<prompt>"`
  - shell   → raw command passed through unchanged
"""

from __future__ import annotations

import shlex
import shutil

_PROVIDER_ALIASES: dict[str, str] = {
    "cursor": "cursor",
    "cursor-agent": "cursor",
    "n/a": "cursor",
    "copilot": "cursor",
    "claude": "claude",
    "claude-code": "claude",
    "shell": "shell",
    "terminal": "shell",
    "bash": "shell",
}

DEFAULT_PROVIDER = "claude"


def normalize_provider(raw: str | None) -> str:
    """Map user input to a canonical provider name.

    Returns one of: 'cursor', 'claude', 'shell'.
    Falls back to DEFAULT_PROVIDER for unknown values.
    """
    if not raw:
        return DEFAULT_PROVIDER
    key = raw.strip().lower()
    return _PROVIDER_ALIASES.get(key, DEFAULT_PROVIDER)


def build_provider_command(*, provider: str, prompt: str) -> str:
    """Return the shell command string that the local agent will execute.

    Args:
        provider: Canonical provider name (from normalize_provider).
        prompt: The user's natural-language prompt.

    Returns:
        A shell-safe command string ready for subprocess execution.
    """
    safe_prompt = shlex.quote(prompt)

    if provider == "cursor":
        cursor_bin = shutil.which("cursor") or "cursor"
        return f"{cursor_bin} --cli agent -p {safe_prompt} --output-format text"

    if provider == "claude":
        claude_bin = shutil.which("claude") or "claude"
        return f"{claude_bin} --dangerously-skip-permissions -p {safe_prompt} --output-format text"

    # shell: pass the prompt as a raw command
    return prompt
