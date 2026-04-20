"""
Tests targeting previously uncovered lines in main.py:
  - _is_affirmation_intent (all branches)
  - _load_state_context (all branches)
  - _classify_reply (all branches)
  - _require_terminal_session_owner (404, 403, happy path)
  - _require_terminal_command_owner (403 path)
  - _require_task_owner (404 path)
  - _require_device_owner (happy path, 404)
  - _background_security_scan (safe auto-approve, high-risk, exception)
  - GET /api/projects/{user_id}
  - POST /api/projects
  - DELETE /api/projects/{project_id}
  - GET /api/phone/status
  - POST /api/phone/send-otp
  - POST /api/phone/verify-otp
  - POST /api/agent/dispatch/{task_id}
  - POST /api/unified/commands
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DEVELOPMENT_MODE", "true")
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "placeholder-key")

from fastapi import HTTPException
from fastapi.testclient import TestClient
from main import (
    app,
    _is_affirmation_intent,
    _load_state_context,
    _classify_reply,
    _require_terminal_session_owner,
    _require_terminal_command_owner,
    _require_task_owner,
    _require_device_owner,
    _background_security_scan,
)

client = TestClient(app)
USER_ID = "test-user-123"


# ---------------------------------------------------------------------------
# _is_affirmation_intent
# ---------------------------------------------------------------------------

class TestIsAffirmationIntent:
    def test_empty_string_returns_false(self):
        # Hits first `if not t: return False` (line 431)
        assert _is_affirmation_intent("") is False

    def test_punctuation_only_returns_false(self):
        # After re.sub, becomes empty → hits second `if not t: return False` (line 435)
        assert _is_affirmation_intent("...") is False

    def test_exact_yes_returns_true(self):
        assert _is_affirmation_intent("yes") is True

    def test_exact_okay_returns_true(self):
        assert _is_affirmation_intent("okay") is True

    def test_exact_approved_returns_true(self):
        assert _is_affirmation_intent("approved") is True

    def test_exact_ship_it_returns_true(self):
        assert _is_affirmation_intent("ship it") is True

    def test_phrase_run_it_returns_true(self):
        # Hits phrase match `return True` (line 452)
        assert _is_affirmation_intent("please run it now") is True

    def test_phrase_go_ahead_returns_true(self):
        assert _is_affirmation_intent("go ahead and do it") is True

    def test_phrase_looks_good_returns_true(self):
        assert _is_affirmation_intent("looks good to me") is True

    def test_unknown_phrase_returns_false(self):
        assert _is_affirmation_intent("maybe later") is False

    def test_very_long_text_no_match_returns_false(self):
        # len > 80, not in exact set → skips phrase check → returns False
        assert _is_affirmation_intent("x" * 90) is False

    def test_uppercase_normalized(self):
        assert _is_affirmation_intent("YES") is True

    def test_with_punctuation_around_exact(self):
        # After stripping punctuation, "yes!" → "yes " → strip → "yes" → in exact
        assert _is_affirmation_intent("yes!") is True


# ---------------------------------------------------------------------------
# _load_state_context
# ---------------------------------------------------------------------------

class TestLoadStateContext:
    def test_none_raw_returns_empty(self):
        assert _load_state_context(None) == {}

    def test_empty_dict_returns_empty(self):
        assert _load_state_context({}) == {}

    def test_missing_context_json_key_returns_empty(self):
        assert _load_state_context({"state": "idle"}) == {}

    def test_none_context_json_returns_empty(self):
        assert _load_state_context({"context_json": None}) == {}

    def test_dict_context_json_returned_directly(self):
        ctx = {"provider": "claude", "session_id": "s1"}
        assert _load_state_context({"context_json": ctx}) == ctx

    def test_valid_json_string_parsed(self):
        result = _load_state_context({"context_json": '{"provider": "shell"}'})
        assert result == {"provider": "shell"}

    def test_invalid_json_string_returns_empty(self):
        assert _load_state_context({"context_json": "not-valid-json"}) == {}

    def test_json_non_dict_returns_empty(self):
        # Valid JSON but not a dict → returns {}
        assert _load_state_context({"context_json": '"just a string"'}) == {}

    def test_integer_context_json_returns_empty(self):
        assert _load_state_context({"context_json": 42}) == {}


# ---------------------------------------------------------------------------
# _classify_reply
# ---------------------------------------------------------------------------

class TestClassifyReply:
    def test_empty_string_returns_empty(self):
        assert _classify_reply("") == "empty"

    def test_whitespace_returns_empty(self):
        assert _classify_reply("   ") == "empty"

    def test_yes_returns_approve(self):
        assert _classify_reply("yes") == "approve"

    def test_ok_returns_approve(self):
        assert _classify_reply("ok") == "approve"

    def test_no_returns_reject(self):
        assert _classify_reply("no") == "reject"

    def test_cancel_returns_reject(self):
        assert _classify_reply("cancel") == "reject"

    def test_stop_returns_reject(self):
        assert _classify_reply("stop") == "reject"

    def test_edit_prefix_returns_edit(self):
        assert _classify_reply("edit the output path") == "edit"

    def test_change_prefix_returns_edit(self):
        assert _classify_reply("change the file name") == "edit"

    def test_instead_prefix_returns_edit(self):
        assert _classify_reply("instead use /tmp") == "edit"

    def test_question_mark_returns_question(self):
        assert _classify_reply("is this safe?") == "question"

    def test_what_prefix_returns_question(self):
        assert _classify_reply("what does this do") == "question"

    def test_why_prefix_returns_question(self):
        assert _classify_reply("why is this needed") == "question"

    def test_how_prefix_returns_question(self):
        assert _classify_reply("how long will it take") == "question"

    def test_unrecognized_returns_unknown(self):
        assert _classify_reply("purple elephant dancing") == "unknown"


# ---------------------------------------------------------------------------
# _require_terminal_session_owner
# ---------------------------------------------------------------------------

class TestRequireTerminalSessionOwner:
    def test_happy_path_returns_session(self):
        session = {"id": "s1", "user_id": USER_ID}
        with patch("database.models.get_terminal_session", return_value=session):
            result = _require_terminal_session_owner(USER_ID, "s1")
        assert result == session

    def test_raises_404_when_not_found(self):
        with patch("database.models.get_terminal_session", return_value=None):
            with pytest.raises(HTTPException) as exc:
                _require_terminal_session_owner(USER_ID, "missing")
        assert exc.value.status_code == 404

    def test_raises_403_when_wrong_owner(self):
        session = {"id": "s1", "user_id": "other-user"}
        with patch("database.models.get_terminal_session", return_value=session):
            with pytest.raises(HTTPException) as exc:
                _require_terminal_session_owner(USER_ID, "s1")
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# _require_terminal_command_owner (403 path)
# ---------------------------------------------------------------------------

class TestRequireTerminalCommandOwner:
    def test_raises_403_when_wrong_owner(self):
        cmd = {"id": "cmd-1", "user_id": "other-user"}
        with patch("database.models.get_terminal_command", return_value=cmd):
            with pytest.raises(HTTPException) as exc:
                _require_terminal_command_owner(USER_ID, "cmd-1")
        assert exc.value.status_code == 403

    def test_happy_path_returns_cmd(self):
        cmd = {"id": "cmd-1", "user_id": USER_ID}
        with patch("database.models.get_terminal_command", return_value=cmd):
            result = _require_terminal_command_owner(USER_ID, "cmd-1")
        assert result == cmd


# ---------------------------------------------------------------------------
# _require_task_owner (404 path)
# ---------------------------------------------------------------------------

class TestRequireTaskOwner:
    def test_raises_404_when_task_not_found(self):
        with patch("database.models.get_task_by_id", return_value=None):
            with pytest.raises(HTTPException) as exc:
                _require_task_owner(USER_ID, "missing-task")
        assert exc.value.status_code == 404

    def test_happy_path_returns_task(self):
        task = {"id": "task-1", "user_id": USER_ID}
        with patch("database.models.get_task_by_id", return_value=task):
            result = _require_task_owner(USER_ID, "task-1")
        assert result == task


# ---------------------------------------------------------------------------
# _require_device_owner
# ---------------------------------------------------------------------------

class TestRequireDeviceOwner:
    def test_happy_path_returns_device(self):
        device = {"id": "dev-1", "user_id": USER_ID}
        with patch("database.models.list_devices_for_user", return_value=[device]):
            result = _require_device_owner(USER_ID, "dev-1")
        assert result == device

    def test_raises_404_when_not_in_list(self):
        with patch("database.models.list_devices_for_user", return_value=[]):
            with pytest.raises(HTTPException) as exc:
                _require_device_owner(USER_ID, "dev-x")
        assert exc.value.status_code == 404

    def test_raises_404_when_wrong_device_id(self):
        device = {"id": "dev-other", "user_id": USER_ID}
        with patch("database.models.list_devices_for_user", return_value=[device]):
            with pytest.raises(HTTPException) as exc:
                _require_device_owner(USER_ID, "dev-x")
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# _background_security_scan
# ---------------------------------------------------------------------------

class TestBackgroundSecurityScan:
    async def test_safe_command_triggers_auto_approve(self):
        safe = {"risk_level": "SAFE", "risk_reason": "benign", "plain_summary": "OK"}
        cmd = {"id": "cmd-1", "user_id": USER_ID, "session_id": "s1", "status": "pending_approval"}
        session = {"id": "s1", "project_id": "p1"}

        with patch("services.security_analyzer.analyze_command_security_with_fallback", new=AsyncMock(return_value=safe)), \
             patch("database.models.update_command_risk_assessment") as mock_risk, \
             patch("database.models.get_terminal_command", return_value=cmd), \
             patch("database.models.update_terminal_command_for_approval", return_value={**cmd, "status": "queued"}) as mock_approve, \
             patch("database.models.get_terminal_session", return_value=session), \
             patch("database.models.add_conversation_turn", return_value={}), \
             patch("database.models.upsert_conversation_state", return_value={}):
            await _background_security_scan("cmd-1", "list files", "ls -la")

        mock_risk.assert_called_once()
        mock_approve.assert_called_once()

    async def test_high_risk_command_does_not_auto_approve(self):
        risky = {"risk_level": "HIGH_RISK", "risk_reason": "rm detected", "plain_summary": "Dangerous"}

        with patch("services.security_analyzer.analyze_command_security_with_fallback", new=AsyncMock(return_value=risky)), \
             patch("database.models.update_command_risk_assessment") as mock_risk, \
             patch("database.models.update_terminal_command_for_approval") as mock_approve:
            await _background_security_scan("cmd-2", "delete", "rm -rf /tmp")

        mock_risk.assert_called_once()
        mock_approve.assert_not_called()

    async def test_warning_does_not_auto_approve(self):
        warning = {"risk_level": "WARNING", "risk_reason": "curl", "plain_summary": "Check this"}

        with patch("services.security_analyzer.analyze_command_security_with_fallback", new=AsyncMock(return_value=warning)), \
             patch("database.models.update_command_risk_assessment"), \
             patch("database.models.update_terminal_command_for_approval") as mock_approve:
            await _background_security_scan("cmd-3", "download", "curl x.com")

        mock_approve.assert_not_called()

    async def test_exception_saves_warning_risk(self):
        with patch("services.security_analyzer.analyze_command_security_with_fallback", new=AsyncMock(side_effect=Exception("LLM down"))), \
             patch("database.models.update_command_risk_assessment") as mock_risk:
            await _background_security_scan("cmd-4", "something", "something")

        mock_risk.assert_called_once()
        _, kwargs = mock_risk.call_args
        assert kwargs.get("risk_level") == "WARNING"

    async def test_safe_command_already_not_pending_skips_approve(self):
        # If command status is not pending_approval, auto-approve is skipped
        safe = {"risk_level": "SAFE", "risk_reason": "benign", "plain_summary": "OK"}
        cmd = {"id": "cmd-5", "user_id": USER_ID, "session_id": "s1", "status": "queued"}

        with patch("services.security_analyzer.analyze_command_security_with_fallback", new=AsyncMock(return_value=safe)), \
             patch("database.models.update_command_risk_assessment"), \
             patch("database.models.get_terminal_command", return_value=cmd), \
             patch("database.models.update_terminal_command_for_approval") as mock_approve:
            await _background_security_scan("cmd-5", "list", "ls")

        mock_approve.assert_not_called()


# ---------------------------------------------------------------------------
# Project routes
# ---------------------------------------------------------------------------

class TestProjectRoutes:
    def test_get_user_projects(self):
        projects = [{"id": "p1", "user_id": USER_ID, "name": "Test"}]
        with patch("database.models.get_user_projects", return_value=projects):
            response = client.get(f"/api/projects/{USER_ID}")
        assert response.status_code == 200
        assert len(response.json()["projects"]) == 1

    def test_get_user_projects_forbidden(self):
        response = client.get("/api/projects/other-user")
        assert response.status_code == 403

    def test_create_project(self):
        with patch("database.models.upsert_user"), \
             patch("database.models.create_project", return_value="proj-new"):
            response = client.post("/api/projects", json={"user_id": USER_ID, "name": "NewApp"})
        assert response.status_code == 200
        assert response.json()["project_id"] == "proj-new"

    def test_create_project_forbidden_for_other_user(self):
        response = client.post("/api/projects", json={"user_id": "other-user", "name": "X"})
        assert response.status_code == 403

    def test_delete_project(self):
        project = {"id": "proj-1", "user_id": USER_ID, "name": "Test"}
        with patch("database.models.get_project_by_id", return_value=project), \
             patch("database.models.delete_project"):
            response = client.delete("/api/projects/proj-1")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_delete_project_forbidden(self):
        other = {"id": "proj-1", "user_id": "other-user"}
        with patch("database.models.get_project_by_id", return_value=other):
            response = client.delete("/api/projects/proj-1")
        assert response.status_code == 403

    def test_delete_project_not_found(self):
        with patch("database.models.get_project_by_id", return_value=None):
            response = client.delete("/api/projects/missing")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Phone endpoints
# ---------------------------------------------------------------------------

class TestPhoneEndpoints:
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

    def test_send_otp_valid_phone(self):
        with patch("services.phone_verification.send_verification", return_value=True):
            response = client.post("/api/phone/send-otp", json={"phone_number": "+12125551234"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_send_otp_invalid_format_returns_400(self):
        # Missing leading +
        response = client.post("/api/phone/send-otp", json={"phone_number": "2125551234"})
        assert response.status_code == 400

    def test_verify_otp_success(self):
        with patch("services.phone_verification.check_verification", return_value=True), \
             patch("database.models.update_user_phone_number"):
            response = client.post("/api/phone/verify-otp", json={"phone_number": "+12125551234", "code": "123456"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_verify_otp_wrong_code(self):
        with patch("services.phone_verification.check_verification", return_value=False):
            response = client.post("/api/phone/verify-otp", json={"phone_number": "+12125551234", "code": "000000"})
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_verify_otp_invalid_phone_format(self):
        response = client.post("/api/phone/verify-otp", json={"phone_number": "bad-number", "code": "123456"})
        assert response.status_code == 400

    def test_verify_otp_value_error_from_model(self):
        with patch("services.phone_verification.check_verification", return_value=True), \
             patch("database.models.update_user_phone_number", side_effect=ValueError("already in use")):
            response = client.post("/api/phone/verify-otp", json={"phone_number": "+12125551234", "code": "123456"})
        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "already in use" in response.json()["error"]


# ---------------------------------------------------------------------------
# Manual dispatch
# ---------------------------------------------------------------------------

class TestManualDispatch:
    def test_manually_dispatch_agent(self):
        task = {"id": "task-1", "user_id": USER_ID, "project_id": "proj-1",
                "description": "Fix bug", "intent_type": "create_task"}
        project = {"id": "proj-1", "user_id": USER_ID, "name": "MyApp"}

        with patch("database.models.get_task_by_id", return_value=task), \
             patch("database.models.get_project_by_id", return_value=project), \
             patch("main.get_terminal_access", return_value=False), \
             patch("main.agent_dispatch_task"):
            response = client.post("/api/agent/dispatch/task-1")

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["task_id"] == "task-1"

    def test_manually_dispatch_forbidden_for_other_user(self):
        other_task = {"id": "task-1", "user_id": "other-user"}
        with patch("database.models.get_task_by_id", return_value=other_task):
            response = client.post("/api/agent/dispatch/task-1")
        assert response.status_code == 403

    def test_manually_dispatch_no_project(self):
        # task has no project_id → intent_data project_name stays None
        task = {"id": "task-2", "user_id": USER_ID, "project_id": None,
                "description": "Do stuff", "intent_type": "create_task"}

        with patch("database.models.get_task_by_id", return_value=task), \
             patch("main.get_terminal_access", return_value=False), \
             patch("main.agent_dispatch_task"):
            response = client.post("/api/agent/dispatch/task-2")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Create unified command
# ---------------------------------------------------------------------------

class TestCreateUnifiedCommand:
    def _common_patches(self, session_id="sess-1", command_id="cmd-new"):
        project = {"id": "proj-1", "user_id": USER_ID, "name": "Test"}
        session = {"id": session_id, "project_id": "proj-1"}
        return (
            patch("database.models.get_project_by_id", return_value=project),
            patch("database.models.get_default_provider_for_user", return_value="shell"),
            patch("database.models.get_or_create_terminal_session_for_project", return_value=session),
            patch("database.models.create_terminal_command", return_value=command_id),
            patch("database.models.add_conversation_turn", return_value={}),
            patch("database.models.upsert_conversation_state", return_value={}),
            patch("services.security_analyzer.analyze_command_security_with_fallback",
                  new=AsyncMock(return_value={"risk_level": "SAFE", "risk_reason": "ok", "plain_summary": "ok"})),
            patch("database.models.update_command_risk_assessment"),
            patch("database.models.get_terminal_command",
                  return_value={"id": command_id, "user_id": USER_ID, "session_id": session_id, "status": "pending_approval"}),
            patch("database.models.update_terminal_command_for_approval", return_value={}),
            patch("database.models.get_terminal_session", return_value=session),
        )

    def test_create_unified_command_success(self):
        patches = self._common_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patches[6], patches[7], patches[8], patches[9], patches[10]:
            response = client.post("/api/unified/commands", json={
                "project_id": "proj-1",
                "prompt": "list files in the project",
                "source": "typed",
            })
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["command_id"] == "cmd-new"

    def test_create_unified_command_empty_prompt(self):
        project = {"id": "proj-1", "user_id": USER_ID, "name": "Test"}
        with patch("database.models.get_project_by_id", return_value=project), \
             patch("database.models.get_default_provider_for_user", return_value="shell"):
            response = client.post("/api/unified/commands", json={
                "project_id": "proj-1",
                "prompt": "   ",
                "source": "typed",
            })
        assert response.status_code == 400

    def test_create_unified_command_forbidden(self):
        other = {"id": "proj-1", "user_id": "other-user"}
        with patch("database.models.get_project_by_id", return_value=other):
            response = client.post("/api/unified/commands", json={
                "project_id": "proj-1",
                "prompt": "test",
                "source": "typed",
            })
        assert response.status_code == 403
