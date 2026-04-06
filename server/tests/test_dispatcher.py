"""Unit tests for agents/dispatcher.py."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

# We patch at the module level so that all calls inside dispatcher use the mock.
MODELS_PATH = "agents.dispatcher.models"


def _make_task(task_id="task-1", user_id="user-1", project_id="proj-1"):
    return {"id": task_id, "user_id": user_id, "project_id": project_id}


def _make_project(project_id="proj-1", name="My Project"):
    return {"id": project_id, "name": name, "file_path": "/tmp/my-project"}


def _make_session(session_id="sess-1"):
    return {"id": session_id}


@pytest.fixture()
def mock_models():
    """Patch the entire models namespace used by dispatcher."""
    with patch(MODELS_PATH) as m:
        # Set sensible defaults so individual tests only override what they need.
        m.create_agent_execution.return_value = "exec-1"
        m.get_task_by_id.return_value = _make_task()
        m.get_project_by_id.return_value = _make_project()
        m.get_user_projects.return_value = [_make_project()]
        m.get_default_provider_for_user.return_value = "claude"
        m.get_or_create_terminal_session_for_project.return_value = _make_session()
        m.create_terminal_command.return_value = "cmd-1"
        m.update_agent_execution.return_value = None
        m.update_task_status.return_value = None
        m.set_task_terminal_session.return_value = None
        yield m


# ==================== terminal access granted ====================


class TestDispatchTaskGranted:
    def test_returns_queued_status(self, mock_models):
        from agents.dispatcher import dispatch_task

        result = dispatch_task("task-1", {"task_description": "fix the bug"}, terminal_granted=True)

        assert result["status"] == "queued"

    def test_returns_correct_keys_on_success(self, mock_models):
        from agents.dispatcher import dispatch_task

        result = dispatch_task("task-1", {"task_description": "add tests"}, terminal_granted=True)

        assert "task_id" in result
        assert "command_id" in result
        assert "session_id" in result
        assert "provider" in result

    def test_creates_agent_execution_at_dispatch_stage(self, mock_models):
        from agents.dispatcher import dispatch_task

        dispatch_task("task-1", {"task_description": "do thing"}, terminal_granted=True)

        mock_models.create_agent_execution.assert_any_call(
            task_id="task-1",
            stage="dispatch",
            agent_type="dispatcher",
            input_prompt="do thing",
            status="running",
        )

    def test_creates_terminal_command(self, mock_models):
        from agents.dispatcher import dispatch_task

        dispatch_task("task-1", {"task_description": "write docs"}, terminal_granted=True)

        mock_models.create_terminal_command.assert_called_once()

    def test_queues_command_with_queued_stage_execution(self, mock_models):
        from agents.dispatcher import dispatch_task

        mock_models.create_agent_execution.return_value = "exec-queued"
        dispatch_task("task-1", {"task_description": "do work"}, terminal_granted=True)

        # Second call to create_agent_execution should use stage="queued"
        calls = mock_models.create_agent_execution.call_args_list
        stages = [c.kwargs.get("stage") or c.args[1] for c in calls]
        assert "queued" in stages

    def test_resolves_project_by_id_from_task(self, mock_models):
        from agents.dispatcher import dispatch_task

        dispatch_task("task-1", {"task_description": "fix"}, terminal_granted=True)

        mock_models.get_project_by_id.assert_called_with("proj-1")

    def test_resolves_project_by_name_when_id_not_found(self, mock_models):
        """If project_id lookup returns None, fall back to name search."""
        mock_models.get_project_by_id.return_value = None
        mock_models.get_user_projects.return_value = [
            {"id": "proj-2", "name": "My App", "file_path": "/tmp/app"}
        ]

        from agents.dispatcher import dispatch_task

        result = dispatch_task(
            "task-1",
            {"task_description": "do thing", "project_name": "My App"},
            terminal_granted=True,
        )

        assert result["status"] == "queued"

    def test_normalizes_provider_from_user_preferences(self, mock_models):
        mock_models.get_default_provider_for_user.return_value = "cursor"

        from agents.dispatcher import dispatch_task

        result = dispatch_task("task-1", {"task_description": "build"}, terminal_granted=True)

        assert result["provider"] == "cursor"

    def test_links_task_to_terminal_session(self, mock_models):
        from agents.dispatcher import dispatch_task

        dispatch_task("task-1", {"task_description": "work"}, terminal_granted=True)

        mock_models.set_task_terminal_session.assert_called_once_with("task-1", "sess-1")

    def test_updates_task_status_to_in_progress(self, mock_models):
        from agents.dispatcher import dispatch_task

        dispatch_task("task-1", {"task_description": "work"}, terminal_granted=True)

        mock_models.update_task_status.assert_any_call("task-1", "in_progress")


# ==================== terminal access NOT granted ====================


class TestDispatchTaskNotGranted:
    def test_returns_pending_status(self, mock_models):
        from agents.dispatcher import dispatch_task

        result = dispatch_task("task-1", {"task_description": "fix"}, terminal_granted=False)

        assert result["status"] == "pending"

    def test_returns_message_terminal_access_not_granted(self, mock_models):
        from agents.dispatcher import dispatch_task

        result = dispatch_task("task-1", {"task_description": "fix"}, terminal_granted=False)

        assert result["message"] == "terminal_access_not_granted"

    def test_does_not_create_terminal_command(self, mock_models):
        from agents.dispatcher import dispatch_task

        dispatch_task("task-1", {"task_description": "fix"}, terminal_granted=False)

        mock_models.create_terminal_command.assert_not_called()

    def test_updates_task_status_to_pending(self, mock_models):
        from agents.dispatcher import dispatch_task

        dispatch_task("task-1", {"task_description": "fix"}, terminal_granted=False)

        mock_models.update_task_status.assert_called_with("task-1", "pending")

    def test_marks_agent_execution_as_success(self, mock_models):
        from agents.dispatcher import dispatch_task

        dispatch_task("task-1", {"task_description": "fix"}, terminal_granted=False)

        # update_agent_execution should be called with status="success" (not failed)
        call_kwargs = [c.kwargs for c in mock_models.update_agent_execution.call_args_list]
        statuses = [kw.get("status") for kw in call_kwargs]
        assert "success" in statuses
        assert "failed" not in statuses


# ==================== missing task ====================


class TestDispatchTaskMissingTask:
    def test_returns_failed_status_when_task_not_found(self, mock_models):
        mock_models.get_task_by_id.return_value = None

        from agents.dispatcher import dispatch_task

        result = dispatch_task("no-such-task", {"task_description": "fix"}, terminal_granted=True)

        assert result["status"] == "failed"
        assert result["error"] == "task_not_found"

    def test_marks_execution_as_failed_when_task_not_found(self, mock_models):
        mock_models.get_task_by_id.return_value = None

        from agents.dispatcher import dispatch_task

        dispatch_task("no-such-task", {"task_description": "fix"}, terminal_granted=True)

        update_calls = mock_models.update_agent_execution.call_args_list
        statuses = [c.kwargs.get("status") for c in update_calls]
        assert "failed" in statuses

    def test_does_not_create_terminal_command_when_task_not_found(self, mock_models):
        mock_models.get_task_by_id.return_value = None

        from agents.dispatcher import dispatch_task

        dispatch_task("no-such-task", {"task_description": "fix"}, terminal_granted=True)

        mock_models.create_terminal_command.assert_not_called()


# ==================== no project found ====================


class TestDispatchTaskNoProject:
    def test_returns_failed_status_when_no_project(self, mock_models):
        mock_models.get_project_by_id.return_value = None
        mock_models.get_user_projects.return_value = []

        from agents.dispatcher import dispatch_task

        result = dispatch_task("task-1", {"task_description": "fix"}, terminal_granted=True)

        assert result["status"] == "failed"
        assert result["error"] == "no_project"

    def test_does_not_create_terminal_command_when_no_project(self, mock_models):
        mock_models.get_project_by_id.return_value = None
        mock_models.get_user_projects.return_value = []

        from agents.dispatcher import dispatch_task

        dispatch_task("task-1", {"task_description": "fix"}, terminal_granted=True)

        mock_models.create_terminal_command.assert_not_called()

    def test_marks_execution_as_failed_when_no_project(self, mock_models):
        mock_models.get_project_by_id.return_value = None
        mock_models.get_user_projects.return_value = []

        from agents.dispatcher import dispatch_task

        dispatch_task("task-1", {"task_description": "fix"}, terminal_granted=True)

        update_calls = mock_models.update_agent_execution.call_args_list
        statuses = [c.kwargs.get("status") for c in update_calls]
        assert "failed" in statuses
