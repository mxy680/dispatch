"""Integration tests for API endpoints using FastAPI TestClient.

DEVELOPMENT_MODE is forced to True in main.py, so the mock user
test-user-123 / test@example.com is used when no Authorization header is sent.

Model calls hit Supabase; we patch get_sb() to return a MagicMock that acts
as a Supabase client, returning controllable data.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

USER_ID = "test-user-123"
GET_SB = "database.models.get_sb"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result(data):
    r = MagicMock()
    r.data = data
    return r


def _make_project(project_id: str = "proj-1", name: str = "Test Project") -> dict:
    return {
        "id": project_id,
        "user_id": USER_ID,
        "name": name,
        "file_path": None,
        "last_accessed": "2024-01-01T00:00:00+00:00",
    }


def _make_session(session_id: str = "sess-1") -> dict:
    return {"id": session_id, "project_id": "proj-1", "user_id": USER_ID}


def _make_command(command_id: str = "cmd-1") -> dict:
    return {
        "id": command_id,
        "command": "claude -p 'fix bug'",
        "status": "queued",
        "user_id": USER_ID,
        "project_id": "proj-1",
    }


def _sb_for_create_project(project_id: str = "proj-1"):
    """Build a mock Supabase that handles create_project + upsert_user calls."""
    sb = MagicMock()
    # upsert_user: select existing → None (new user path), then insert
    sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _result(None)
    sb.table.return_value.insert.return_value.execute.return_value = _result(None)
    # create_project: insert
    sb.table.return_value.upsert.return_value.execute.return_value = _result(None)
    # get_project_base_path_for_user (via get_user_preferences → upsert + select)
    prefs_result = _result({"user_id": USER_ID, "project_base_path": None})
    sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = prefs_result
    # device links: select returns empty
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value = _result([])
    return sb


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


class TestRoot:
    def test_get_root_returns_status(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "status" in response.json()


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class TestProjectsEndpoints:
    def test_create_project_returns_project_id(self):
        new_pid = str(uuid.uuid4())

        # Patch the individual model functions called by the endpoint
        with patch("database.models.upsert_user"), \
             patch("database.models.create_project", return_value=new_pid):
            response = client.post(
                "/api/projects",
                json={"user_id": USER_ID, "name": "API Test Project"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["project_id"] == new_pid

    def test_get_user_projects_returns_list(self):
        projects = [_make_project("proj-1", "Proj Alpha")]

        with patch("database.models.get_user_projects", return_value=projects):
            response = client.get(f"/api/projects/{USER_ID}")

        assert response.status_code == 200
        body = response.json()
        assert "projects" in body
        assert body["projects"][0]["name"] == "Proj Alpha"

    def test_get_user_projects_other_user_returns_403(self):
        response = client.get("/api/projects/other-user-id")
        assert response.status_code == 403

    def test_delete_project_returns_success(self):
        project = _make_project("proj-to-delete")

        with patch("database.models.get_project_by_id", return_value=project), \
             patch("database.models.delete_project"):
            response = client.delete("/api/projects/proj-to-delete")

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_delete_nonexistent_project_returns_404(self):
        with patch("database.models.get_project_by_id", return_value=None):
            response = client.delete("/api/projects/nonexistent-project-id")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Unified Commands
# ---------------------------------------------------------------------------


class TestUnifiedCommandsEndpoints:
    def test_queue_command_returns_success(self):
        project = _make_project()
        session = _make_session()
        cmd_id = "cmd-new"

        with patch("database.models.get_project_by_id", return_value=project), \
             patch("database.models.get_default_provider_for_user", return_value="claude"), \
             patch("database.models.get_or_create_terminal_session_for_project", return_value=session), \
             patch("database.models.create_terminal_command", return_value=cmd_id), \
             patch("database.models.add_conversation_turn"), \
             patch("database.models.upsert_conversation_state"):
            response = client.post(
                "/api/unified/commands",
                json={"project_id": "proj-1", "prompt": "fix the login bug", "provider": "claude"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["command_id"] == cmd_id
        assert body["session_id"] == session["id"]

    def test_queue_command_empty_prompt_returns_400(self):
        project = _make_project()

        with patch("database.models.get_project_by_id", return_value=project), \
             patch("database.models.get_default_provider_for_user", return_value="claude"), \
             patch("database.models.add_conversation_turn"), \
             patch("database.models.upsert_conversation_state"):
            response = client.post(
                "/api/unified/commands",
                json={"project_id": "proj-1", "prompt": "   "},
            )

        assert response.status_code == 400

    def test_queue_command_unknown_project_returns_404(self):
        with patch("database.models.get_project_by_id", return_value=None), \
             patch("database.models.add_conversation_turn"), \
             patch("database.models.upsert_conversation_state"):
            response = client.post(
                "/api/unified/commands",
                json={"project_id": "does-not-exist", "prompt": "do something"},
            )

        assert response.status_code == 404

    def test_get_timeline_returns_commands_list(self):
        commands = [_make_command("cmd-1"), _make_command("cmd-2")]

        with patch("database.models.list_recent_terminal_commands_for_user", return_value=commands):
            response = client.get("/api/unified/timeline")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["commands"], list)
        assert len(body["commands"]) == 2

    def test_queue_command_starts_pending_approval(self):
        project = _make_project()
        session = _make_session()
        cmd_id = "cmd-pa"
        with patch("database.models.get_project_by_id", return_value=project), \
             patch("database.models.get_default_provider_for_user", return_value="claude"), \
             patch("database.models.get_or_create_terminal_session_for_project", return_value=session), \
             patch("database.models.create_terminal_command", return_value=cmd_id) as create_cmd, \
             patch("database.models.add_conversation_turn"), \
             patch("database.models.upsert_conversation_state"):
            response = client.post(
                "/api/unified/commands",
                json={"project_id": "proj-1", "prompt": "list files", "provider": "claude"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "pending_approval"
        assert create_cmd.call_args.kwargs["status"] == "pending_approval"

    def test_approve_pending_command(self):
        cmd = {"id": "cmd-1", "user_id": USER_ID, "session_id": "sess-1", "status": "pending_approval"}
        session = {"id": "sess-1", "project_id": "proj-1"}
        with patch("database.models.get_terminal_command", return_value=cmd), \
             patch("database.models.get_terminal_session", return_value=session), \
             patch("database.models.update_terminal_command_for_approval", return_value={**cmd, "status": "queued"}), \
             patch("database.models.add_conversation_turn"), \
             patch("database.models.upsert_conversation_state"):
            response = client.post("/api/unified/commands/cmd-1/approval", json={"action": "approve"})

        assert response.status_code == 200
        assert response.json()["command"]["status"] == "queued"


# ---------------------------------------------------------------------------
# Phone OTP
# ---------------------------------------------------------------------------


class TestPhoneEndpoints:
    def test_send_otp_success(self):
        with patch("services.phone_verification.send_verification", return_value=True):
            response = client.post(
                "/api/phone/send-otp",
                json={"phone_number": "+12125551234"},
            )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_send_otp_invalid_format_returns_400(self):
        response = client.post(
            "/api/phone/send-otp",
            json={"phone_number": "555-1234"},
        )
        assert response.status_code == 400

    def test_send_otp_twilio_failure_returns_502(self):
        with patch("services.phone_verification.send_verification", return_value=False):
            response = client.post(
                "/api/phone/send-otp",
                json={"phone_number": "+12125551234"},
            )
        assert response.status_code == 502

    def test_verify_otp_correct_code_returns_success(self):
        with patch("services.phone_verification.check_verification", return_value=True), \
             patch("database.models.update_user_phone_number", return_value=None):
            response = client.post(
                "/api/phone/verify-otp",
                json={"phone_number": "+12125551234", "code": "123456"},
            )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_verify_otp_wrong_code_returns_failure(self):
        with patch("services.phone_verification.check_verification", return_value=False):
            response = client.post(
                "/api/phone/verify-otp",
                json={"phone_number": "+12125551234", "code": "000000"},
            )
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_verify_otp_invalid_format_returns_400(self):
        response = client.post(
            "/api/phone/verify-otp",
            json={"phone_number": "not-a-phone", "code": "123456"},
        )
        assert response.status_code == 400

    def test_phone_status_no_phone(self):
        with patch("database.models.get_user_phone_number", return_value=None):
            response = client.get("/api/phone/status")
        assert response.status_code == 200
        assert response.json()["has_phone"] is False

    def test_phone_status_with_phone(self):
        with patch("database.models.get_user_phone_number", return_value="+12125551234"):
            response = client.get("/api/phone/status")
        assert response.status_code == 200
        assert response.json()["has_phone"] is True
