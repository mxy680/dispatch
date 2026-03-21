"""
Agent dispatcher — takes a parsed task/intent and queues it for execution.

Pipeline stages tracked in agent_executions:
  1. dispatch  — validate task, resolve project, build command
  2. queued    — terminal command created and waiting for a local agent to claim

The local agent daemon (or companion) picks up the queued command,
executes it, streams logs, and marks it complete.
"""

from __future__ import annotations

import logging
import time

from agents.command_builder import build_provider_command, normalize_provider
from database import models

logger = logging.getLogger("dispatch.dispatcher")


def dispatch_task(task_id: str, intent_data: dict, terminal_granted: bool) -> dict:
    """Dispatch a task through the agent pipeline.

    1. Look up the task and its project.
    2. If terminal access is granted, build a provider command and queue it.
    3. Track progress via agent_executions.

    Returns a summary dict with status and any created command_id.
    """
    start_ms = _now_ms()

    # --- Stage 1: Dispatch (validate + resolve) ---
    exec_id = models.create_agent_execution(
        task_id=task_id,
        stage="dispatch",
        agent_type="dispatcher",
        input_prompt=intent_data.get("task_description", ""),
        status="running",
    )

    task = models.get_task_by_id(task_id)
    if not task:
        models.update_agent_execution(
            exec_id,
            status="failed",
            error_message=f"Task {task_id} not found",
            execution_time_ms=_elapsed_ms(start_ms),
        )
        return {"status": "failed", "error": "task_not_found"}

    user_id = task.get("user_id", "")
    project_id = task.get("project_id")
    project_name = intent_data.get("project_name")
    task_description = intent_data.get("task_description", "")

    # Resolve project
    project = None
    if project_id:
        project = models.get_project_by_id(project_id)
    if not project and project_name:
        projects = models.get_user_projects(user_id)
        for p in projects:
            if p.get("name", "").lower() == project_name.lower():
                project = p
                project_id = p["id"]
                break

    if not terminal_granted:
        models.update_agent_execution(
            exec_id,
            status="success",
            output_result="Terminal access not granted — task recorded but not executed",
            explanation="User has not enabled terminal access. The task is saved and can be dispatched manually once access is granted.",
            execution_time_ms=_elapsed_ms(start_ms),
        )
        models.update_task_status(task_id, "pending")
        return {
            "status": "pending",
            "message": "terminal_access_not_granted",
            "task_id": task_id,
        }

    if not project:
        models.update_agent_execution(
            exec_id,
            status="failed",
            error_message="No project found for this task. Create a project first.",
            execution_time_ms=_elapsed_ms(start_ms),
        )
        return {"status": "failed", "error": "no_project"}

    # Determine provider
    raw_provider = models.get_default_provider_for_user(user_id)
    provider = normalize_provider(raw_provider)

    # Build the CLI command
    command_str = build_provider_command(provider=provider, prompt=task_description)

    models.update_agent_execution(
        exec_id,
        status="success",
        output_result=f"Resolved project={project.get('name')}, provider={provider}",
        execution_time_ms=_elapsed_ms(start_ms),
    )

    # --- Stage 2: Queue terminal command ---
    queue_start = _now_ms()
    queue_exec_id = models.create_agent_execution(
        task_id=task_id,
        stage="queued",
        agent_type="dispatcher",
        input_prompt=task_description,
        refined_prompt=command_str,
        status="running",
    )

    session = models.get_or_create_terminal_session_for_project(
        user_id=user_id,
        project_id=project_id,
        name="Agent Session",
    )

    command_id = models.create_terminal_command(
        session_id=session["id"],
        user_id=user_id,
        command=command_str,
        source="agent",
        provider=provider,
        user_prompt=task_description,
        normalized_command=command_str,
    )

    # Link the task to its terminal session
    models.set_task_terminal_session(task_id, session["id"])
    models.update_task_status(task_id, "in_progress")

    models.update_agent_execution(
        queue_exec_id,
        status="success",
        output_result=f"Command queued: command_id={command_id}",
        terminal_command_id=command_id,
        execution_time_ms=_elapsed_ms(queue_start),
    )

    logger.info(
        "dispatch_task complete task_id=%s project=%s provider=%s command_id=%s",
        task_id,
        project.get("name"),
        provider,
        command_id,
    )

    return {
        "status": "queued",
        "task_id": task_id,
        "command_id": command_id,
        "session_id": session["id"],
        "provider": provider,
    }


def set_terminal_access(user_id: str, granted: bool) -> None:
    """Persist whether a user has granted terminal access."""
    from agents.copilot_agent import set_terminal_access as _set
    _set(user_id, granted)


def get_terminal_access(user_id: str) -> bool:
    """Read whether a user has granted terminal access."""
    from agents.copilot_agent import get_terminal_access as _get
    return _get(user_id)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _elapsed_ms(start_ms: int) -> int:
    return _now_ms() - start_ms
