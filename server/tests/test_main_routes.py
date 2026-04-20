"""
Tests for previously uncovered routes in main.py.

Covers:
  - /api/settings/* (agent tokens, history, provider, base path)
  - /api/call-sessions/{user_id}
  - /api/agent/status, /api/agent/executions, /api/agent/terminal-access
  - /api/tasks (create, update)
  - /api/unified/timeline, /api/unified/conversation
  - /api/unified/commands (create, approval)
  - /api/projects/{project_id}/tasks, /api/dashboard
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DEVELOPMENT_MODE", "true")
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "placeholder-key")

from main import app

client = TestClient(app)
USER_ID = "test-user-123"


def _make_project(pid="proj-1"):
    return {"id": pid, "user_id": USER_ID, "name": "Test", "file_path": None}


def _make_task(tid="task-1"):
    return {"id": tid, "user_id": USER_ID, "project_id": "proj-1", "description": "Fix bug", "status": "pending"}


def _make_command(cid="cmd-1"):
    return {"id": cid, "user_id": USER_ID, "session_id": "sess-1", "status": "pending_approval", "command": "ls"}


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------

class TestSettingsEndpoints:
    def test_list_agent_tokens(self):
        with patch("database.models.list_agent_tokens", return_value=[{"id": "tok-1", "label": "ci"}]):
            response = client.get("/api/settings/agent-tokens")
        assert response.status_code == 200
        assert response.json()["tokens"][0]["label"] == "ci"

    def test_create_agent_token(self):
        fake_token = {"id": "tok-2", "label": "prod", "token": "abc123"}
        with patch("database.models.upsert_user"), \
             patch("database.models.create_agent_token", return_value=fake_token):
            response = client.post("/api/settings/agent-tokens", json={"label": "prod"})
        assert response.status_code == 200
        assert response.json()["label"] == "prod"

    def test_revoke_agent_token(self):
        with patch("database.models.revoke_agent_token"):
            response = client.delete("/api/settings/agent-tokens/tok-1")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_delete_history(self):
        with patch("database.models.delete_user_history", return_value={"tasks": 3}):
            response = client.delete("/api/settings/history")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_get_provider_preference(self):
        with patch("database.models.upsert_user"), \
             patch("database.models.get_default_provider_for_user", return_value="claude"):
            response = client.get("/api/settings/provider")
        assert response.status_code == 200
        assert response.json()["provider"] == "claude"

    def test_set_provider_preference(self):
        with patch("database.models.upsert_user"), \
             patch("database.models.set_default_provider_for_user"):
            response = client.put("/api/settings/provider", json={"provider": "cursor"})
        assert response.status_code == 200
        assert response.json()["provider"] == "cursor"

    def test_get_project_base_path(self):
        with patch("database.models.get_project_base_path_for_user", return_value="/home/user/projects"), \
             patch("database.models._ensure_user_preferences_row"):
            response = client.get("/api/settings/project-base-path")
        assert response.status_code == 200
        assert response.json()["base_path"] == "/home/user/projects"

    def test_set_project_base_path(self):
        with patch("database.models.set_project_base_path_for_user"), \
             patch("database.models.get_project_base_path_for_user", return_value="/home/user/projects"), \
             patch("database.models._ensure_user_preferences_row"):
            response = client.put("/api/settings/project-base-path", json={"base_path": "/home/user/projects"})
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_get_dashboard_returns_projects_and_tasks(self):
        with patch("database.models.get_user_projects_with_task_counts", return_value=[_make_project()]), \
             patch("database.models.get_user_tasks", return_value=[_make_task()]):
            response = client.get(f"/api/dashboard/{USER_ID}")
        assert response.status_code == 200
        body = response.json()
        assert "projects" in body
        assert "tasks" in body

    def test_get_dashboard_forbidden_for_other_user(self):
        response = client.get("/api/dashboard/other-user")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Project tasks
# ---------------------------------------------------------------------------

class TestProjectTasks:
    def test_get_project_tasks(self):
        with patch("database.models.get_project_by_id", return_value=_make_project()), \
             patch("database.models.get_project_tasks", return_value=[_make_task()]):
            response = client.get("/api/projects/proj-1/tasks")
        assert response.status_code == 200
        assert len(response.json()["tasks"]) == 1

    def test_get_project_tasks_forbidden(self):
        other_project = {**_make_project(), "user_id": "other-user"}
        with patch("database.models.get_project_by_id", return_value=other_project):
            response = client.get("/api/projects/proj-1/tasks")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class TestTasksEndpoints:
    def test_create_task(self):
        with patch("database.models.get_project_by_id", return_value=_make_project()), \
             patch("database.models.create_task", return_value="task-new"), \
             patch("main.get_terminal_access", return_value=False):
            response = client.post("/api/tasks", json={
                "user_id": USER_ID,
                "project_id": "proj-1",
                "description": "Fix the bug",
            })
        assert response.status_code == 200
        assert response.json()["task_id"] == "task-new"

    def test_create_task_missing_user_id_returns_400(self):
        response = client.post("/api/tasks", json={
            "user_id": "",
            "project_id": "proj-1",
            "description": "Fix",
        })
        assert response.status_code == 400

    def test_update_task_status(self):
        with patch("database.models.get_task_by_id", return_value=_make_task()), \
             patch("database.models.update_task_status"):
            response = client.patch("/api/tasks/task-1", json={"status": "completed"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_update_task_forbidden(self):
        other_task = {**_make_task(), "user_id": "other-user"}
        with patch("database.models.get_task_by_id", return_value=other_task):
            response = client.patch("/api/tasks/task-1", json={"status": "completed"})
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Call sessions
# ---------------------------------------------------------------------------

class TestCallSessions:
    def test_get_call_history(self):
        with patch("database.models.get_user_call_history", return_value=[{"id": "s1"}]):
            response = client.get(f"/api/call-sessions/{USER_ID}")
        assert response.status_code == 200
        assert len(response.json()["sessions"]) == 1

    def test_get_call_history_forbidden(self):
        response = client.get("/api/call-sessions/other-user")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Agent pipeline endpoints
# ---------------------------------------------------------------------------

class TestAgentEndpoints:
    def test_get_agent_status(self):
        with patch("database.models.get_task_by_id", return_value=_make_task()), \
             patch("database.models.get_agent_executions", return_value=[]), \
             patch("database.models.get_task_agent_status", return_value={"stage": "queued"}):
            response = client.get("/api/agent/status/task-1")
        assert response.status_code == 200
        assert response.json()["task_id"] == "task-1"

    def test_get_agent_executions(self):
        with patch("database.models.get_user_agent_executions", return_value=[{"id": "exec-1"}]):
            response = client.get(f"/api/agent/executions/{USER_ID}")
        assert response.status_code == 200
        assert len(response.json()["executions"]) == 1

    def test_get_agent_executions_forbidden(self):
        response = client.get("/api/agent/executions/other-user")
        assert response.status_code == 403

    def test_grant_terminal_access(self):
        with patch("main.set_terminal_access"):
            response = client.post(f"/api/agent/terminal-access/{USER_ID}")
        assert response.status_code == 200
        assert response.json()["terminal_access"] is True

    def test_revoke_terminal_access(self):
        with patch("main.set_terminal_access"):
            response = client.delete(f"/api/agent/terminal-access/{USER_ID}")
        assert response.status_code == 200
        assert response.json()["terminal_access"] is False

    def test_check_terminal_access(self):
        with patch("main.get_terminal_access", return_value=True):
            response = client.get(f"/api/agent/terminal-access/{USER_ID}")
        assert response.status_code == 200
        assert response.json()["terminal_access"] is True

    def test_terminal_access_forbidden_for_other_user(self):
        response = client.get("/api/agent/terminal-access/other-user")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Unified timeline / conversation
# ---------------------------------------------------------------------------

class TestUnifiedEndpoints:
    def test_get_unified_timeline(self):
        with patch("database.models.list_recent_terminal_commands_for_user", return_value=[_make_command()]):
            response = client.get("/api/unified/timeline")
        assert response.status_code == 200
        assert len(response.json()["commands"]) == 1

    def test_get_unified_timeline_filtered_by_project(self):
        cmds = [
            {**_make_command("cmd-1"), "project_id": "proj-1"},
            {**_make_command("cmd-2"), "project_id": "proj-2"},
        ]
        with patch("database.models.list_recent_terminal_commands_for_user", return_value=cmds):
            response = client.get("/api/unified/timeline?project_id=proj-1")
        assert len(response.json()["commands"]) == 1

    def test_get_unified_conversation(self):
        with patch("database.models.list_conversation_turns_for_user", return_value=[{"id": "turn-1"}]):
            response = client.get("/api/unified/conversation")
        assert response.status_code == 200
        assert len(response.json()["turns"]) == 1


# ---------------------------------------------------------------------------
# Unified command approval
# ---------------------------------------------------------------------------

class TestApprovalEndpoints:
    def test_approve_command(self):
        cmd = _make_command()
        updated = {**cmd, "status": "queued"}
        session = {"id": "sess-1", "project_id": "proj-1"}

        with patch("database.models.get_terminal_command", return_value=cmd), \
             patch("database.models.update_terminal_command_for_approval", return_value=updated), \
             patch("database.models.get_terminal_session", return_value=session), \
             patch("database.models.add_conversation_turn", return_value={}), \
             patch("database.models.upsert_conversation_state", return_value={}):
            response = client.post("/api/unified/commands/cmd-1/approval", json={"action": "approve"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_reject_command(self):
        cmd = _make_command()
        updated = {**cmd, "status": "cancelled"}
        session = {"id": "sess-1", "project_id": "proj-1"}

        with patch("database.models.get_terminal_command", return_value=cmd), \
             patch("database.models.update_terminal_command_for_approval", return_value=updated), \
             patch("database.models.get_terminal_session", return_value=session), \
             patch("database.models.add_conversation_turn", return_value={}), \
             patch("database.models.upsert_conversation_state", return_value={}):
            response = client.post("/api/unified/commands/cmd-1/approval", json={"action": "reject"})
        assert response.status_code == 200

    def test_approval_command_not_found_returns_404(self):
        with patch("database.models.get_terminal_command", return_value=None):
            response = client.post("/api/unified/commands/bad-cmd/approval", json={"action": "approve"})
        assert response.status_code == 404

    def test_approval_wrong_status_returns_400(self):
        cmd = {**_make_command(), "status": "completed"}
        with patch("database.models.get_terminal_command", return_value=cmd):
            response = client.post("/api/unified/commands/cmd-1/approval", json={"action": "approve"})
        assert response.status_code == 400
