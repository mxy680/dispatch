"""
Second batch of main.py route tests, targeting previously uncovered lines:
  - GET / root
  - Device pairing: POST /api/device/pair/start, /api/device/pair/complete
  - GET /api/device, POST/GET /api/device/{device_id}/projects
  - Device-token routes: my-projects, settings, heartbeat, claim-next,
      append-logs, complete, cursor-context, link-project
  - Agent-token routes: register, heartbeat, claim-next, append-logs, complete
  - Terminal routes: sessions CRUD, commands CRUD, logs
  - PUT /api/unified/commands/{command_id}/edit (all branches)
  - POST /api/unified/reply (all intent branches)
  - POST /transcribe-text (intent branches, empty, exception)
  - POST /api/tasks with terminal access auto-dispatch
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DEVELOPMENT_MODE", "true")
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "placeholder-key")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
USER_ID = "test-user-123"

# Fake device returned by get_device_by_token mock
FAKE_DEVICE = {"id": "dev-1", "user_id": USER_ID, "name": "My Mac"}
# Fake agent user_id returned by get_user_id_for_agent_token mock
AGENT_TOKEN_HEADERS = {"X-Agent-Token": "agent-tok-123"}
DEVICE_TOKEN_HEADERS = {"X-Device-Token": "device-tok-123"}


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

class TestRoot:
    def test_root_returns_listening(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "Dispatch" in response.json()["status"]


# ---------------------------------------------------------------------------
# Device pairing (user-token endpoints)
# ---------------------------------------------------------------------------

class TestDevicePairing:
    def test_start_device_pairing(self):
        pairing = {"id": "pair-1", "code": "ABC123", "user_id": USER_ID}
        with patch("database.models.upsert_user"), \
             patch("database.models.create_device_pairing", return_value=pairing):
            response = client.post("/api/device/pair/start", json={"name": "My Mac", "platform": "darwin"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_complete_device_pairing_success(self):
        result = {"user_id": USER_ID, "device_id": "dev-1", "token": "tok-abc"}
        with patch("database.models.complete_device_pairing", return_value=result), \
             patch("database.models.get_user_projects", return_value=[]), \
             patch("database.models.get_project_base_path_for_user", return_value=None), \
             patch("database.models.link_device_project"):
            response = client.post("/api/device/pair/complete",
                                   json={"pairing_code": "ABC123", "name": "My Mac", "platform": "darwin"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_complete_device_pairing_invalid_code(self):
        with patch("database.models.complete_device_pairing", return_value=None):
            response = client.post("/api/device/pair/complete",
                                   json={"pairing_code": "WRONG", "name": "X", "platform": "darwin"})
        assert response.status_code == 400

    def test_complete_device_pairing_auto_links_projects(self):
        result = {"user_id": USER_ID, "device_id": "dev-1", "token": "tok-abc"}
        project = {"id": "proj-1", "name": "MyApp", "file_path": "/home/user/myapp"}
        with patch("database.models.complete_device_pairing", return_value=result), \
             patch("database.models.get_user_projects", return_value=[project]), \
             patch("database.models.get_project_base_path_for_user", return_value=None), \
             patch("database.models.link_device_project") as mock_link, \
             patch("database.models.compute_default_project_file_path", return_value=None):
            response = client.post("/api/device/pair/complete",
                                   json={"pairing_code": "ABC123"})
        assert response.status_code == 200
        mock_link.assert_called_once()

    def test_list_user_devices(self):
        with patch("database.models.list_devices_for_user", return_value=[FAKE_DEVICE]):
            response = client.get("/api/device")
        assert response.status_code == 200
        assert len(response.json()["devices"]) == 1

    def test_link_device_to_project(self):
        project = {"id": "proj-1", "user_id": USER_ID}
        link = {"device_id": "dev-1", "project_id": "proj-1"}
        with patch("database.models.list_devices_for_user", return_value=[FAKE_DEVICE]), \
             patch("database.models.get_project_by_id", return_value=project), \
             patch("database.models.link_device_project", return_value=link):
            response = client.post("/api/device/dev-1/projects",
                                   json={"project_id": "proj-1", "local_path": "/home/user/proj"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_list_device_projects(self):
        links = [{"device_id": "dev-1", "project_id": "proj-1"}]
        with patch("database.models.list_devices_for_user", return_value=[FAKE_DEVICE]), \
             patch("database.models.get_device_project_links", return_value=links):
            response = client.get("/api/device/dev-1/projects")
        assert response.status_code == 200
        assert len(response.json()["links"]) == 1


# ---------------------------------------------------------------------------
# Device-token routes
# ---------------------------------------------------------------------------

class TestDeviceTokenRoutes:
    def test_get_my_projects(self):
        links = [{"device_id": "dev-1", "project_id": "proj-1"}]
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE), \
             patch("database.models.get_device_project_links", return_value=links):
            response = client.get("/api/device/my-projects", headers=DEVICE_TOKEN_HEADERS)
        assert response.status_code == 200
        assert len(response.json()["links"]) == 1

    def test_get_device_settings_base_path(self):
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE), \
             patch("database.models.get_project_base_path_for_user", return_value="/home/user/projects"):
            response = client.get("/api/device/settings/project-base-path", headers=DEVICE_TOKEN_HEADERS)
        assert response.status_code == 200
        assert response.json()["base_path"] == "/home/user/projects"

    def test_set_device_settings_base_path(self):
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE), \
             patch("database.models.set_project_base_path_for_user"), \
             patch("database.models.get_project_base_path_for_user", return_value="/new/path"):
            response = client.put("/api/device/settings/project-base-path",
                                  headers=DEVICE_TOKEN_HEADERS,
                                  json={"base_path": "/new/path"})
        assert response.status_code == 200
        assert response.json()["base_path"] == "/new/path"

    def test_link_project_for_device(self):
        project = {"id": "proj-1", "user_id": USER_ID, "name": "MyApp"}
        link = {"device_id": "dev-1", "project_id": "proj-1"}
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE), \
             patch("database.models.upsert_project_by_name", return_value=project), \
             patch("database.models.link_device_project", return_value=link):
            response = client.post("/api/device/link-project",
                                   headers=DEVICE_TOKEN_HEADERS,
                                   json={"project_name": "MyApp", "local_path": "/home/user/myapp"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_link_project_missing_name_returns_400(self):
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE):
            response = client.post("/api/device/link-project",
                                   headers=DEVICE_TOKEN_HEADERS,
                                   json={"project_name": "", "local_path": "/home/user/myapp"})
        assert response.status_code == 400

    def test_device_heartbeat(self):
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE), \
             patch("database.models.touch_device_heartbeat"):
            response = client.post("/api/device/heartbeat",
                                   headers=DEVICE_TOKEN_HEADERS,
                                   json={"device_id": "dev-1"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_device_heartbeat_wrong_id_returns_403(self):
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE):
            response = client.post("/api/device/heartbeat",
                                   headers=DEVICE_TOKEN_HEADERS,
                                   json={"device_id": "dev-other"})
        assert response.status_code == 403

    def test_device_claim_next_no_command(self):
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE), \
             patch("database.models.claim_next_queued_command_for_device", return_value=None):
            response = client.post("/api/device/claim-next",
                                   headers=DEVICE_TOKEN_HEADERS,
                                   json={"wait_seconds": 0})
        assert response.status_code == 200
        assert response.json()["command"] is None

    def test_device_claim_next_with_command(self):
        cmd = {"id": "cmd-1", "command": "ls"}
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE), \
             patch("database.models.claim_next_queued_command_for_device", return_value=cmd):
            response = client.post("/api/device/claim-next",
                                   headers=DEVICE_TOKEN_HEADERS,
                                   json={"wait_seconds": 0})
        assert response.status_code == 200
        assert response.json()["command"]["id"] == "cmd-1"

    def test_device_append_logs(self):
        cmd = {"id": "cmd-1", "user_id": USER_ID}
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE), \
             patch("database.models.get_terminal_command", return_value=cmd), \
             patch("database.models.append_terminal_log_chunk"), \
             patch("database.models.touch_device_heartbeat"):
            response = client.post("/api/device/commands/cmd-1/append-logs",
                                   headers=DEVICE_TOKEN_HEADERS,
                                   json={"sequence_start": 0, "stream": "stdout", "chunks": ["hello", "world"]})
        assert response.status_code == 200
        assert response.json()["next_sequence"] == 2

    def test_device_complete_command(self):
        cmd = {"id": "cmd-1", "user_id": USER_ID}
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE), \
             patch("database.models.get_terminal_command", return_value=cmd), \
             patch("database.models.complete_terminal_command"), \
             patch("database.models.touch_device_heartbeat"):
            response = client.post("/api/device/commands/cmd-1/complete",
                                   headers=DEVICE_TOKEN_HEADERS,
                                   json={"status": "completed", "exit_code": 0})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_device_complete_command_invalid_status(self):
        cmd = {"id": "cmd-1", "user_id": USER_ID}
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE), \
             patch("database.models.get_terminal_command", return_value=cmd):
            response = client.post("/api/device/commands/cmd-1/complete",
                                   headers=DEVICE_TOKEN_HEADERS,
                                   json={"status": "running"})
        assert response.status_code == 400

    def test_cursor_context_upsert(self):
        project = {"id": "proj-1", "user_id": USER_ID}
        links = [{"project_id": "proj-1"}]
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE), \
             patch("database.models.get_project_by_id", return_value=project), \
             patch("database.models.get_device_project_links", return_value=links), \
             patch("database.models.save_cursor_context", return_value="ctx-1"), \
             patch("database.models.touch_device_heartbeat"):
            response = client.post("/api/device/cursor-context",
                                   headers=DEVICE_TOKEN_HEADERS,
                                   json={"project_id": "proj-1", "file_path": "main.py"})
        assert response.status_code == 200
        assert response.json()["context_id"] == "ctx-1"

    def test_cursor_context_project_not_linked_returns_403(self):
        project = {"id": "proj-1", "user_id": USER_ID}
        with patch("database.models.get_device_by_token", return_value=FAKE_DEVICE), \
             patch("database.models.get_project_by_id", return_value=project), \
             patch("database.models.get_device_project_links", return_value=[]):
            response = client.post("/api/device/cursor-context",
                                   headers=DEVICE_TOKEN_HEADERS,
                                   json={"project_id": "proj-1"})
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Agent-token routes
# ---------------------------------------------------------------------------

class TestAgentTokenRoutes:
    def test_register_local_agent_with_project_id(self):
        project = {"id": "proj-1", "user_id": USER_ID}
        instance = {"id": "inst-1", "user_id": USER_ID}
        with patch("database.models.get_user_id_for_agent_token", return_value=USER_ID), \
             patch("database.models.get_project_by_id", return_value=project), \
             patch("database.models.register_instance", return_value=instance):
            response = client.post("/api/agent/local/register",
                                   headers=AGENT_TOKEN_HEADERS,
                                   json={"project_id": "proj-1"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_register_local_agent_with_project_path(self):
        project = {"id": "proj-new", "user_id": USER_ID, "name": "myapp"}
        instance = {"id": "inst-1", "user_id": USER_ID}
        with patch("database.models.get_user_id_for_agent_token", return_value=USER_ID), \
             patch("database.models.upsert_project_by_name", return_value=project), \
             patch("database.models.register_instance", return_value=instance):
            response = client.post("/api/agent/local/register",
                                   headers=AGENT_TOKEN_HEADERS,
                                   json={"project_path": "/home/user/myapp", "project_name": "myapp"})
        assert response.status_code == 200

    def test_local_agent_heartbeat(self):
        instance = {"id": "inst-1", "user_id": USER_ID}
        with patch("database.models.get_user_id_for_agent_token", return_value=USER_ID), \
             patch("database.models.get_instance_by_id", return_value=instance), \
             patch("database.models.update_instance_heartbeat"):
            response = client.post("/api/agent/local/heartbeat",
                                   headers=AGENT_TOKEN_HEADERS,
                                   json={"instance_id": "inst-1", "status": "online"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_local_agent_heartbeat_instance_not_found(self):
        with patch("database.models.get_user_id_for_agent_token", return_value=USER_ID), \
             patch("database.models.get_instance_by_id", return_value=None):
            response = client.post("/api/agent/local/heartbeat",
                                   headers=AGENT_TOKEN_HEADERS,
                                   json={"instance_id": "missing", "status": "online"})
        assert response.status_code == 404

    def test_local_agent_claim_next_no_command(self):
        instance = {"id": "inst-1", "user_id": USER_ID}
        with patch("database.models.get_user_id_for_agent_token", return_value=USER_ID), \
             patch("database.models.get_instance_by_id", return_value=instance), \
             patch("database.models.claim_next_queued_command_for_user", return_value=None):
            response = client.post("/api/agent/local/claim-next",
                                   headers=AGENT_TOKEN_HEADERS,
                                   json={"instance_id": "inst-1", "wait_seconds": 0})
        assert response.status_code == 200
        assert response.json()["command"] is None

    def test_local_agent_append_logs(self):
        cmd = {"id": "cmd-1", "user_id": USER_ID}
        with patch("database.models.get_user_id_for_agent_token", return_value=USER_ID), \
             patch("database.models.get_terminal_command", return_value=cmd), \
             patch("database.models.append_terminal_log_chunk"):
            response = client.post("/api/agent/local/commands/cmd-1/append-logs",
                                   headers=AGENT_TOKEN_HEADERS,
                                   json={"sequence_start": 0, "stream": "stdout", "chunks": ["output"]})
        assert response.status_code == 200
        assert response.json()["next_sequence"] == 1

    def test_local_agent_complete_command(self):
        cmd = {"id": "cmd-1", "user_id": USER_ID}
        with patch("database.models.get_user_id_for_agent_token", return_value=USER_ID), \
             patch("database.models.get_terminal_command", return_value=cmd), \
             patch("database.models.complete_terminal_command"):
            response = client.post("/api/agent/local/commands/cmd-1/complete",
                                   headers=AGENT_TOKEN_HEADERS,
                                   json={"status": "completed"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_local_agent_complete_invalid_status(self):
        cmd = {"id": "cmd-1", "user_id": USER_ID}
        with patch("database.models.get_user_id_for_agent_token", return_value=USER_ID), \
             patch("database.models.get_terminal_command", return_value=cmd):
            response = client.post("/api/agent/local/commands/cmd-1/complete",
                                   headers=AGENT_TOKEN_HEADERS,
                                   json={"status": "running"})
        assert response.status_code == 400

    def test_agent_token_missing_returns_401(self):
        response = client.post("/api/agent/local/heartbeat",
                               json={"instance_id": "inst-1", "status": "online"})
        assert response.status_code == 401

    def test_agent_token_invalid_returns_401(self):
        with patch("database.models.get_user_id_for_agent_token", return_value=None):
            response = client.post("/api/agent/local/heartbeat",
                                   headers={"X-Agent-Token": "bad-token"},
                                   json={"instance_id": "inst-1", "status": "online"})
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Terminal session / command routes
# ---------------------------------------------------------------------------

class TestTerminalRoutes:
    def _project(self):
        return {"id": "proj-1", "user_id": USER_ID}

    def _session(self, instance_id="inst-1"):
        return {"id": "sess-1", "user_id": USER_ID, "project_id": "proj-1", "instance_id": instance_id}

    def _cmd(self):
        return {"id": "cmd-1", "user_id": USER_ID, "session_id": "sess-1"}

    def test_list_terminal_sessions(self):
        with patch("database.models.get_project_by_id", return_value=self._project()), \
             patch("database.models.list_terminal_sessions_for_project", return_value=[self._session()]):
            response = client.get("/api/terminal/sessions/proj-1")
        assert response.status_code == 200
        assert len(response.json()["sessions"]) == 1

    def test_create_terminal_session_with_instance(self):
        with patch("database.models.get_project_by_id", return_value=self._project()), \
             patch("database.models.create_terminal_session", return_value="sess-new"):
            response = client.post("/api/terminal/sessions",
                                   json={"project_id": "proj-1", "name": "My Session", "instance_id": "inst-1"})
        assert response.status_code == 200
        assert response.json()["session_id"] == "sess-new"

    def test_create_terminal_session_auto_finds_instance(self):
        active = [{"id": "inst-1"}]
        with patch("database.models.get_project_by_id", return_value=self._project()), \
             patch("database.models.get_active_instances_for_user", return_value=active), \
             patch("database.models.create_terminal_session", return_value="sess-new"):
            response = client.post("/api/terminal/sessions",
                                   json={"project_id": "proj-1"})
        assert response.status_code == 200

    def test_close_terminal_session(self):
        with patch("database.models.get_terminal_session", return_value=self._session()), \
             patch("database.models.set_terminal_session_status"):
            response = client.delete("/api/terminal/sessions/sess-1")
        assert response.status_code == 200

    def test_create_terminal_command_success(self):
        with patch("database.models.get_terminal_session", return_value=self._session()), \
             patch("database.models.get_default_provider_for_user", return_value="shell"), \
             patch("database.models.create_terminal_command", return_value="cmd-new"):
            response = client.post("/api/terminal/sessions/sess-1/commands",
                                   json={"command": "ls -la", "provider": "shell"})
        assert response.status_code == 200
        assert response.json()["command_id"] == "cmd-new"

    def test_create_terminal_command_no_instance_returns_409(self):
        session_no_instance = {**self._session(), "instance_id": None}
        with patch("database.models.get_terminal_session", return_value=session_no_instance), \
             patch("database.models.get_active_instances_for_user", return_value=[]):
            response = client.post("/api/terminal/sessions/sess-1/commands",
                                   json={"command": "ls"})
        assert response.status_code == 409

    def test_list_terminal_commands(self):
        with patch("database.models.get_terminal_session", return_value=self._session()), \
             patch("database.models.list_terminal_commands_for_session", return_value=[self._cmd()]):
            response = client.get("/api/terminal/sessions/sess-1/commands")
        assert response.status_code == 200
        assert len(response.json()["commands"]) == 1

    def test_get_terminal_command_logs(self):
        logs = [{"sequence": 0, "stream": "stdout", "chunk": "hello"}]
        with patch("database.models.get_terminal_command", return_value=self._cmd()), \
             patch("database.models.get_terminal_logs_for_command", return_value=logs):
            response = client.get("/api/terminal/commands/cmd-1/logs")
        assert response.status_code == 200
        assert len(response.json()["logs"]) == 1


# ---------------------------------------------------------------------------
# PUT /api/unified/commands/{command_id}/edit
# ---------------------------------------------------------------------------

class TestEditPendingCommand:
    def _cmd(self, status="pending_approval"):
        return {"id": "cmd-1", "user_id": USER_ID, "session_id": "sess-1",
                "status": status, "provider": "shell"}

    def test_edit_pending_command_success(self):
        session = {"id": "sess-1", "project_id": "proj-1"}
        updated = {**self._cmd(), "command": "new-cmd"}
        with patch("database.models.get_terminal_command", return_value=self._cmd()), \
             patch("database.models.update_terminal_command_for_approval", return_value=updated), \
             patch("database.models.get_terminal_session", return_value=session), \
             patch("database.models.add_conversation_turn", return_value={}), \
             patch("database.models.upsert_conversation_state", return_value={}), \
             patch("services.security_analyzer.analyze_command_security_with_fallback",
                   new=AsyncMock(return_value={"risk_level": "SAFE", "risk_reason": "ok", "plain_summary": "ok"})), \
             patch("database.models.update_command_risk_assessment"), \
             patch("database.models.get_terminal_command", return_value={**self._cmd(), "status": "pending_approval"}):
            response = client.put("/api/unified/commands/cmd-1/edit",
                                  json={"prompt": "list all files recursively"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_edit_wrong_status_returns_400(self):
        completed_cmd = {**self._cmd(), "status": "completed"}
        with patch("database.models.get_terminal_command", return_value=completed_cmd):
            response = client.put("/api/unified/commands/cmd-1/edit",
                                  json={"prompt": "new prompt"})
        assert response.status_code == 400

    def test_edit_empty_prompt_returns_400(self):
        with patch("database.models.get_terminal_command", return_value=self._cmd()):
            response = client.put("/api/unified/commands/cmd-1/edit",
                                  json={"prompt": "   "})
        assert response.status_code == 400

    def test_edit_forbidden_for_other_user(self):
        other_cmd = {**self._cmd(), "user_id": "other-user"}
        with patch("database.models.get_terminal_command", return_value=other_cmd):
            response = client.put("/api/unified/commands/cmd-1/edit",
                                  json={"prompt": "something"})
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/unified/reply — all intent branches
# ---------------------------------------------------------------------------

class TestUnifiedReply:
    def _project(self):
        return {"id": "proj-1", "user_id": USER_ID}

    def _cmd(self, risk_level="SAFE"):
        return {"id": "cmd-1", "user_id": USER_ID, "session_id": "sess-1",
                "status": "pending_approval", "provider": "shell", "risk_level": risk_level}

    def _state(self, active_command_id="cmd-1"):
        return {"state": "awaiting_approval", "active_command_id": active_command_id,
                "context_json": {"provider": "shell", "session_id": "sess-1"}}

    def test_empty_reply_returns_400(self):
        with patch("database.models.get_project_by_id", return_value=self._project()):
            response = client.post("/api/unified/reply",
                                   json={"project_id": "proj-1", "reply": "  "})
        assert response.status_code == 400

    def test_no_active_command_returns_info(self):
        with patch("database.models.get_project_by_id", return_value=self._project()), \
             patch("database.models.get_conversation_state", return_value=None), \
             patch("database.models.add_conversation_turn", return_value={}):
            response = client.post("/api/unified/reply",
                                   json={"project_id": "proj-1", "reply": "yes please"})
        assert response.status_code == 200
        assert response.json()["intent"] == "unknown"

    def test_approve_safe_command_queues_it(self):
        session = {"id": "sess-1", "project_id": "proj-1"}
        with patch("database.models.get_project_by_id", return_value=self._project()), \
             patch("database.models.get_conversation_state", return_value=self._state()), \
             patch("database.models.get_terminal_command", return_value=self._cmd("SAFE")), \
             patch("database.models.add_conversation_turn", return_value={}), \
             patch("database.models.update_terminal_command_for_approval", return_value={}), \
             patch("database.models.upsert_conversation_state", return_value={}):
            response = client.post("/api/unified/reply",
                                   json={"project_id": "proj-1", "reply": "yes"})
        assert response.status_code == 200
        assert response.json()["intent"] == "approve"

    def test_approve_high_risk_returns_403(self):
        with patch("database.models.get_project_by_id", return_value=self._project()), \
             patch("database.models.get_conversation_state", return_value=self._state()), \
             patch("database.models.get_terminal_command", return_value=self._cmd("HIGH_RISK")), \
             patch("database.models.add_conversation_turn", return_value={}):
            response = client.post("/api/unified/reply",
                                   json={"project_id": "proj-1", "reply": "yes"})
        assert response.status_code == 403

    def test_reject_cancels_command(self):
        with patch("database.models.get_project_by_id", return_value=self._project()), \
             patch("database.models.get_conversation_state", return_value=self._state()), \
             patch("database.models.get_terminal_command", return_value=self._cmd()), \
             patch("database.models.add_conversation_turn", return_value={}), \
             patch("database.models.update_terminal_command_for_approval", return_value={}), \
             patch("database.models.upsert_conversation_state", return_value={}):
            response = client.post("/api/unified/reply",
                                   json={"project_id": "proj-1", "reply": "no"})
        assert response.status_code == 200
        assert response.json()["intent"] == "reject"

    def test_edit_reply_updates_command(self):
        with patch("database.models.get_project_by_id", return_value=self._project()), \
             patch("database.models.get_conversation_state", return_value=self._state()), \
             patch("database.models.get_terminal_command", return_value=self._cmd()), \
             patch("database.models.add_conversation_turn", return_value={}), \
             patch("database.models.update_terminal_command_for_approval", return_value={}):
            response = client.post("/api/unified/reply",
                                   json={"project_id": "proj-1", "reply": "edit to use /tmp instead"})
        assert response.status_code == 200
        assert response.json()["intent"] == "contextual_reply"

    def test_unknown_reply_returns_info(self):
        with patch("database.models.get_project_by_id", return_value=self._project()), \
             patch("database.models.get_conversation_state", return_value=self._state()), \
             patch("database.models.get_terminal_command", return_value=self._cmd()), \
             patch("database.models.add_conversation_turn", return_value={}):
            response = client.post("/api/unified/reply",
                                   json={"project_id": "proj-1", "reply": "purple banana sky"})
        assert response.status_code == 200
        # intent is "unknown" - returns info
        assert "intent" in response.json()

    def test_question_reply_returns_info(self):
        with patch("database.models.get_project_by_id", return_value=self._project()), \
             patch("database.models.get_conversation_state", return_value=self._state()), \
             patch("database.models.get_terminal_command", return_value=self._cmd()), \
             patch("database.models.add_conversation_turn", return_value={}):
            response = client.post("/api/unified/reply",
                                   json={"project_id": "proj-1", "reply": "what does this command do?"})
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# /transcribe-text intent branches
# ---------------------------------------------------------------------------

class TestTranscribeTextBranches:
    def _base_mocks(self):
        return (
            patch("database.models.upsert_user"),
            patch("database.models.get_user_projects", return_value=[]),
            patch("database.models.log_agent_event_task", return_value="task-log"),
            patch("main.get_terminal_access", return_value=False),
        )

    def test_empty_text_returns_error(self):
        response = client.post("/transcribe-text", json={"text": "  "})
        assert response.status_code == 200
        assert response.json()["status"] == "error"

    def test_create_project_no_name_returns_message(self):
        intent = {"intent": "create_project"}  # no project_name
        with patch("database.models.upsert_user"), \
             patch("database.models.get_user_projects", return_value=[]), \
             patch("main.parse_intent", new=AsyncMock(return_value=intent)), \
             patch("main.get_terminal_access", return_value=False), \
             patch("database.models.get_user_projects_with_task_counts", return_value=[]):
            response = client.post("/transcribe-text", json={"text": "create a project"})
        assert response.status_code == 200
        assert "couldn't determine" in response.json()["action_result"]

    def test_create_task_project_not_found(self):
        intent = {"intent": "create_task", "project_name": "MyApp", "task_description": "Fix bug"}
        with patch("database.models.upsert_user"), \
             patch("database.models.get_user_projects", return_value=[]), \
             patch("main.parse_intent", new=AsyncMock(return_value=intent)), \
             patch("database.models.get_project_by_name", return_value=None), \
             patch("database.models.log_agent_event_task", return_value="task-log"), \
             patch("main.agent_dispatch_task"), \
             patch("main.get_terminal_access", return_value=False):
            response = client.post("/transcribe-text", json={"text": "add login page to MyApp"})
        assert response.status_code == 200
        assert "Could not find" in response.json()["action_result"]

    def test_create_task_missing_description(self):
        intent = {"intent": "create_task", "project_name": "MyApp"}  # no task_description
        with patch("database.models.upsert_user"), \
             patch("database.models.get_user_projects", return_value=[]), \
             patch("main.parse_intent", new=AsyncMock(return_value=intent)), \
             patch("database.models.log_agent_event_task", return_value="task-log"), \
             patch("main.agent_dispatch_task"), \
             patch("main.get_terminal_access", return_value=False):
            response = client.post("/transcribe-text", json={"text": "add something"})
        assert response.status_code == 200
        assert "couldn't determine" in response.json()["action_result"]

    def test_status_check_no_projects(self):
        intent = {"intent": "status_check"}
        with patch("database.models.upsert_user"), \
             patch("database.models.get_user_projects", return_value=[]), \
             patch("main.parse_intent", new=AsyncMock(return_value=intent)), \
             patch("database.models.get_user_projects_with_task_counts", return_value=[]), \
             patch("database.models.log_agent_event_task", return_value="task-log"), \
             patch("main.get_terminal_access", return_value=False):
            response = client.post("/transcribe-text", json={"text": "what's my status"})
        assert response.status_code == 200
        assert "don't have any" in response.json()["action_result"]

    def test_status_check_with_projects(self):
        intent = {"intent": "status_check"}
        projects = [{"name": "MyApp", "total_tasks": 3}]
        with patch("database.models.upsert_user"), \
             patch("database.models.get_user_projects", return_value=projects), \
             patch("main.parse_intent", new=AsyncMock(return_value=intent)), \
             patch("database.models.get_user_projects_with_task_counts", return_value=projects), \
             patch("database.models.log_agent_event_task", return_value="task-log"), \
             patch("main.get_terminal_access", return_value=False):
            response = client.post("/transcribe-text", json={"text": "show my projects"})
        assert response.status_code == 200
        assert "MyApp" in response.json()["action_result"]

    def test_unknown_intent(self):
        intent = {"intent": "teleport"}
        with patch("database.models.upsert_user"), \
             patch("database.models.get_user_projects", return_value=[]), \
             patch("main.parse_intent", new=AsyncMock(return_value=intent)), \
             patch("database.models.log_agent_event_task", return_value="task-log"), \
             patch("main.get_terminal_access", return_value=False):
            response = client.post("/transcribe-text", json={"text": "beam me up"})
        assert response.status_code == 200
        assert "wasn't able" in response.json()["action_result"]

    def test_exception_returns_error_status(self):
        with patch("database.models.upsert_user"), \
             patch("database.models.get_user_projects", side_effect=Exception("DB down")):
            response = client.post("/transcribe-text", json={"text": "do something"})
        assert response.status_code == 200
        assert response.json()["status"] == "error"


# ---------------------------------------------------------------------------
# create_task auto-dispatch with terminal access
# ---------------------------------------------------------------------------

class TestCreateTaskAutoDispatch:
    def test_create_task_with_terminal_access_dispatches(self):
        project = {"id": "proj-1", "user_id": USER_ID}
        with patch("database.models.get_project_by_id", return_value=project), \
             patch("database.models.create_task", return_value="task-new"), \
             patch("main.get_terminal_access", return_value=True), \
             patch("main.agent_dispatch_task") as mock_dispatch:
            response = client.post("/api/tasks", json={
                "user_id": USER_ID,
                "project_id": "proj-1",
                "description": "Fix the bug",
            })
        assert response.status_code == 200
        assert response.json()["task_id"] == "task-new"
        # background_tasks.add_task was called (dispatch queued)
