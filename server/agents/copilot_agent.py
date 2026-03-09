"""
Stub copilot agent module.
TODO: Implement actual Claude Code orchestration logic.
"""

_terminal_access: dict[str, bool] = {}


def dispatch_task(task_id: str, intent_data: dict, terminal_granted: bool) -> dict:
    """Dispatch a task to the agent pipeline. Currently a no-op stub."""
    print(f"[copilot_agent] STUB dispatch_task called: task_id={task_id}, terminal={terminal_granted}")
    print(f"[copilot_agent] Intent: {intent_data}")
    return {
        "status": "stub",
        "message": "Agent pipeline not yet implemented",
        "task_id": task_id,
    }


def set_terminal_access(user_id: str, granted: bool) -> None:
    """Set whether a user has granted terminal access."""
    _terminal_access[user_id] = granted


def get_terminal_access(user_id: str) -> bool:
    """Check whether a user has granted terminal access."""
    return _terminal_access.get(user_id, False)
