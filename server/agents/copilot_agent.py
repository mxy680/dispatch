"""
Stub copilot agent module.
TODO: Implement actual Claude Code orchestration logic.
"""

from database.supabase_client import get_sb


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
    """Persist whether a user has granted terminal access to the database."""
    sb = get_sb()
    sb.table("user_preferences").upsert(
        {"user_id": user_id, "terminal_access": granted},
        on_conflict="user_id",
    ).execute()


def get_terminal_access(user_id: str) -> bool:
    """Read whether a user has granted terminal access from the database."""
    sb = get_sb()
    res = (
        sb.table("user_preferences")
        .select("terminal_access")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if res and res.data:
        return bool(res.data.get("terminal_access", False))
    return False
