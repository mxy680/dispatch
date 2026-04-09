"""
Unit tests for database model functions.

These tests mock `database.models.get_sb` (the bound name inside models.py)
so no real Supabase connection is needed.
"""
import pytest
from unittest.mock import patch, MagicMock
from database import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chain(data, *, data_single=None):
    """Return a fully chainable Supabase mock whose final .execute().data == data."""
    result = MagicMock()
    result.data = data

    result_single = MagicMock()
    result_single.data = data_single

    c = MagicMock()
    c.execute.return_value = result
    c.eq.return_value = c
    c.neq.return_value = c
    c.order.return_value = c
    c.limit.return_value = c
    c.select.return_value = c
    c.insert.return_value = c
    c.update.return_value = c
    c.upsert.return_value = c
    c.delete.return_value = c
    c.ilike.return_value = c
    single_chain = MagicMock()
    single_chain.execute.return_value = result_single
    single_chain.eq.return_value = single_chain
    single_chain.neq.return_value = single_chain
    single_chain.order.return_value = single_chain
    single_chain.limit.return_value = single_chain
    single_chain.select.return_value = single_chain
    single_chain.insert.return_value = single_chain
    single_chain.update.return_value = single_chain
    single_chain.upsert.return_value = single_chain
    single_chain.delete.return_value = single_chain
    single_chain.ilike.return_value = single_chain
    c.maybe_single.return_value = single_chain
    return c


def _mock_sb(data=None, *, data_single=None):
    sb = MagicMock()
    sb.table.return_value = _chain(data or [], data_single=data_single)
    return sb


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class TestProjects:

    def test_create_project_calls_insert(self):
        """create_project should insert a row and return its id."""
        fake_id = "proj-001"
        fake_row = {"id": fake_id, "name": "My App", "user_id": "user-1", "file_path": None}

        with patch("database.models.get_sb", return_value=_mock_sb([fake_row])), \
             patch("database.models.get_project_base_path_for_user", return_value="/tmp/dispatch-projects"), \
             patch("database.models.get_project_by_id", return_value=fake_row):
            pid = models.create_project("user-1", "My App")

        assert pid is not None

    def test_get_user_projects_returns_list(self):
        """get_user_projects should return a list of project dicts."""
        fake_projects = [
            {"id": "p1", "name": "Project A", "user_id": "user-1"},
            {"id": "p2", "name": "Project B", "user_id": "user-1"},
        ]
        with patch("database.models.get_sb", return_value=_mock_sb(fake_projects)):
            projects = models.get_user_projects("user-1")

        assert len(projects) == 2
        assert projects[0]["name"] == "Project A"

    def test_get_project_by_name_returns_none_when_missing(self):
        """get_project_by_name should return None when the query result is empty."""
        # maybe_single().execute().data == None means not found
        result = MagicMock()
        result.data = None
        c = MagicMock()
        c.execute.return_value = result
        c.ilike.return_value = c
        c.eq.return_value = c
        c.select.return_value = c
        c.maybe_single.return_value = c
        sb = MagicMock()
        sb.table.return_value = c

        with patch("database.models.get_sb", return_value=sb):
            found = models.get_project_by_name("user-1", "nonexistent")

        assert found is None

    def test_get_project_by_name_scoped_to_user(self):
        """get_project_by_name should return the row that belongs to the queried user."""
        fake_row = {"id": "p1", "name": "Shared Name", "user_id": "user-1"}
        result = MagicMock()
        result.data = fake_row
        c = MagicMock()
        c.execute.return_value = result
        c.ilike.return_value = c
        c.eq.return_value = c
        c.select.return_value = c
        c.maybe_single.return_value = c
        sb = MagicMock()
        sb.table.return_value = c

        with patch("database.models.get_sb", return_value=sb):
            result_row = models.get_project_by_name("user-1", "Shared Name")

        assert result_row["user_id"] == "user-1"


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class TestTasks:

    def test_create_task_returns_id(self):
        """create_task should call Supabase insert and return a task id."""
        fake_task_id = "task-999"
        with patch("database.models.get_sb", return_value=_mock_sb([{"id": fake_task_id}])):
            tid = models.create_task("proj-1", "user-1", "Fix bug")
        assert tid is not None

    def test_get_project_tasks_returns_tasks(self):
        """get_project_tasks should return the tasks list from Supabase."""
        fake_tasks = [
            {"id": "t1", "project_id": "p1", "description": "Fix bug", "status": "pending"},
        ]
        with patch("database.models.get_sb", return_value=_mock_sb(fake_tasks)):
            tasks = models.get_project_tasks("p1")

        assert len(tasks) == 1
        assert tasks[0]["description"] == "Fix bug"

    def test_update_task_status_calls_supabase(self):
        """update_task_status should call supabase update without raising."""
        sb = _mock_sb([{"id": "t1", "status": "completed"}])
        with patch("database.models.get_sb", return_value=sb):
            models.update_task_status("t1", "completed")
        sb.table.assert_called()


# ---------------------------------------------------------------------------
# Call Sessions
# ---------------------------------------------------------------------------

class TestCallSessions:

    def test_create_call_session_returns_id(self):
        """create_call_session should return the new session id string."""
        fake_row = {"id": "session-abc", "user_id": "user-1"}
        with patch("database.models.get_sb", return_value=_mock_sb([fake_row])):
            sid = models.create_call_session("user-1", "+15551234567")
        assert sid is not None


class TestApprovalConversationModels:
    def test_create_terminal_command_accepts_pending_approval_status(self):
        sb = _mock_sb([])
        with patch("database.models.get_sb", return_value=sb), patch(
            "database.sidecar_store.set_command_risk"
        ) as risk_mock:
            cid = models.create_terminal_command(
                session_id="s1",
                user_id="u1",
                command="echo hi",
                status="pending_approval",
            )
        assert cid
        payload = sb.table.return_value.insert.call_args[0][0]
        assert payload["status"] == "pending_approval"
        assert "risk_level" not in payload
        risk_mock.assert_called_once_with(
            command_id=cid,
            user_id="u1",
            risk_level="PENDING",
            risk_reason=None,
            plain_summary="I prepared this action and I am waiting for your approval before I run it.",
        )

    def test_add_conversation_turn_writes_expected_fields(self):
        with patch("database.sidecar_store.add_conversation_turn") as add_turn:
            add_turn.return_value = {
                "id": "t1",
                "user_id": "u1",
                "project_id": "p1",
                "session_id": "s1",
                "command_id": "c1",
                "role": "assistant",
                "turn_type": "approval_request",
                "content": "Approve this command",
                "created_at": "2024-01-01T00:00:00+00:00",
            }
            row = models.add_conversation_turn(
                user_id="u1",
                project_id="p1",
                session_id="s1",
                command_id="c1",
                role="assistant",
                turn_type="approval_request",
                content="Approve this command",
            )
        add_turn.assert_called_once_with(
            user_id="u1",
            project_id="p1",
            session_id="s1",
            command_id="c1",
            role="assistant",
            turn_type="approval_request",
            content="Approve this command",
        )
        assert row["role"] == "assistant"
        assert row["turn_type"] == "approval_request"


# ---------------------------------------------------------------------------
# Pure helper functions — no mocking needed
# ---------------------------------------------------------------------------

class TestNormalizeConversationStateRow:
    def test_none_input_returns_none(self):
        from database.models import _normalize_conversation_state_row
        assert _normalize_conversation_state_row(None) is None

    def test_empty_project_id_becomes_none(self):
        from database.models import _normalize_conversation_state_row
        row = {"project_id": "", "other": "val"}
        result = _normalize_conversation_state_row(row)
        assert result["project_id"] is None
        assert result["other"] == "val"

    def test_non_empty_project_id_unchanged(self):
        from database.models import _normalize_conversation_state_row
        row = {"project_id": "proj-1", "other": "val"}
        result = _normalize_conversation_state_row(row)
        assert result["project_id"] == "proj-1"


class TestFirstOrNone:
    def test_none_input_returns_none(self):
        from database.models import _first_or_none
        assert _first_or_none(None) is None

    def test_empty_list_returns_none(self):
        from database.models import _first_or_none
        res = MagicMock()
        res.data = []
        assert _first_or_none(res) is None

    def test_list_with_item_returns_first(self):
        from database.models import _first_or_none
        res = MagicMock()
        res.data = [{"id": "a"}, {"id": "b"}]
        assert _first_or_none(res)["id"] == "a"

    def test_dict_data_returns_dict(self):
        from database.models import _first_or_none
        res = MagicMock()
        res.data = {"id": "a"}
        assert _first_or_none(res)["id"] == "a"

    def test_none_data_attribute_returns_none(self):
        from database.models import _first_or_none
        res = MagicMock()
        res.data = None
        assert _first_or_none(res) is None


class TestSafeProjectFolderName:
    def test_normal_name_unchanged(self):
        from database.models import _safe_project_folder_name
        assert _safe_project_folder_name("my-project") == "my-project"

    def test_spaces_replaced_with_dash(self):
        from database.models import _safe_project_folder_name
        assert _safe_project_folder_name("My Project") == "My-Project"

    def test_slashes_replaced(self):
        from database.models import _safe_project_folder_name
        result = _safe_project_folder_name("a/b\\c")
        assert "/" not in result
        assert "\\" not in result

    def test_empty_string_returns_project(self):
        from database.models import _safe_project_folder_name
        assert _safe_project_folder_name("") == "Project"

    def test_special_chars_stripped(self):
        from database.models import _safe_project_folder_name
        result = _safe_project_folder_name("hello@world!")
        assert "@" not in result
        assert "!" not in result


class TestComputeDefaultProjectFilePath:
    def test_none_base_path_returns_none(self):
        from database.models import compute_default_project_file_path
        assert compute_default_project_file_path(None, "MyProject") is None

    def test_relative_base_path_returns_none(self):
        from database.models import compute_default_project_file_path
        assert compute_default_project_file_path("relative/path", "MyProject") is None

    def test_absolute_base_path_returns_joined_path(self):
        from database.models import compute_default_project_file_path
        result = compute_default_project_file_path("/home/user/projects", "My App")
        assert result == "/home/user/projects/My-App"

    def test_empty_base_path_returns_none(self):
        from database.models import compute_default_project_file_path
        assert compute_default_project_file_path("", "MyProject") is None


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------

class TestUserOperations:
    def test_upsert_user_inserts_new_user(self):
        sb = _mock_sb(data_single=None)  # no existing user
        with patch("database.models.get_sb", return_value=sb):
            models.upsert_user("user-new", "new@example.com")
        sb.table.return_value.insert.assert_called_once()

    def test_upsert_user_updates_existing_user(self):
        sb = _mock_sb(data_single={"id": "user-existing"})
        with patch("database.models.get_sb", return_value=sb):
            models.upsert_user("user-existing", "existing@example.com")
        sb.table.return_value.update.assert_called()

    def test_upsert_user_includes_phone_when_provided(self):
        sb = _mock_sb(data_single=None)
        with patch("database.models.get_sb", return_value=sb):
            models.upsert_user("u1", "a@b.com", phone_number="+15550001111")
        insert_payload = sb.table.return_value.insert.call_args[0][0]
        assert insert_payload["phone_number"] == "+15550001111"

    def test_get_user_id_by_telegram_chat_id_found(self):
        sb = _mock_sb([{"id": "user-123"}])
        with patch("database.models.get_sb", return_value=sb):
            result = models.get_user_id_by_telegram_chat_id("456")
        assert result == "user-123"

    def test_get_user_id_by_telegram_chat_id_not_found(self):
        sb = _mock_sb([])
        with patch("database.models.get_sb", return_value=sb):
            result = models.get_user_id_by_telegram_chat_id("999")
        assert result is None

    def test_get_user_phone_number_returns_phone(self):
        sb = _mock_sb([{"phone_number": "+15559876543"}])
        with patch("database.models.get_sb", return_value=sb):
            result = models.get_user_phone_number("user-1")
        assert result == "+15559876543"

    def test_get_user_phone_number_returns_none_when_missing(self):
        sb = _mock_sb([])
        with patch("database.models.get_sb", return_value=sb):
            result = models.get_user_phone_number("user-1")
        assert result is None

    def test_get_user_id_by_phone_found(self):
        sb = _mock_sb([{"id": "user-abc"}])
        with patch("database.models.get_sb", return_value=sb):
            result = models.get_user_id_by_phone("+15550001111")
        assert result == "user-abc"

    def test_get_user_id_by_phone_not_found(self):
        sb = _mock_sb([])
        with patch("database.models.get_sb", return_value=sb):
            result = models.get_user_id_by_phone("+19999999999")
        assert result is None

    def test_update_user_phone_raises_on_duplicate(self):
        sb = MagicMock()
        sb.table.return_value.update.return_value.eq.return_value.execute.side_effect = Exception("unique constraint 23505")
        with patch("database.models.get_sb", return_value=sb):
            with pytest.raises(ValueError, match="already linked"):
                models.update_user_phone_number("user-1", "+15550001111")


# ---------------------------------------------------------------------------
# Project operations
# ---------------------------------------------------------------------------

class TestProjectOperations:
    def test_touch_project_calls_update(self):
        sb = _mock_sb()
        with patch("database.models.get_sb", return_value=sb):
            models.touch_project("proj-1")
        sb.table.return_value.update.assert_called_once()

    def test_get_project_by_id_returns_row(self):
        fake = {"id": "proj-1", "name": "Test"}
        sb = _mock_sb(data_single=fake)
        with patch("database.models.get_sb", return_value=sb):
            result = models.get_project_by_id("proj-1")
        assert result["name"] == "Test"

    def test_delete_project_calls_delete_on_projects_table(self):
        sb = _mock_sb([])
        with patch("database.models.get_sb", return_value=sb):
            models.delete_project("proj-1")
        # Verify projects table was deleted
        calls = [str(c) for c in sb.table.call_args_list]
        assert any("projects" in c for c in calls)

    def test_get_user_tasks_flattens_project_name(self):
        fake_tasks = [{"id": "t1", "projects": {"name": "MyApp"}, "description": "fix bug"}]
        sb = _mock_sb(fake_tasks)
        with patch("database.models.get_sb", return_value=sb):
            tasks = models.get_user_tasks("user-1")
        assert tasks[0]["project_name"] == "MyApp"
        assert "projects" not in tasks[0]

    def test_get_user_tasks_handles_no_project(self):
        fake_tasks = [{"id": "t1", "projects": None, "description": "fix bug"}]
        sb = _mock_sb(fake_tasks)
        with patch("database.models.get_sb", return_value=sb):
            tasks = models.get_user_tasks("user-1")
        assert tasks[0]["project_name"] is None


# ---------------------------------------------------------------------------
# User preferences
# ---------------------------------------------------------------------------

class TestUserPreferences:
    def _prefs_sb(self, prefs: dict):
        """Return a mock sb that yields prefs row from user_preferences."""
        sb = MagicMock()
        result = MagicMock()
        result.data = prefs
        chain = MagicMock()
        chain.execute.return_value = result
        chain.eq.return_value = chain
        chain.select.return_value = chain
        chain.upsert.return_value = chain
        chain.update.return_value = chain
        chain.maybe_single.return_value = chain
        chain.limit.return_value = chain
        sb.table.return_value = chain
        return sb

    def test_get_default_provider_returns_cursor_for_unknown(self):
        sb = self._prefs_sb({"default_provider": "unknown-tool"})
        with patch("database.models.get_sb", return_value=sb), \
             patch("database.models._ensure_user_preferences_row"):
            result = models.get_default_provider_for_user("user-1")
        assert result == "cursor"

    def test_get_default_provider_returns_claude(self):
        sb = self._prefs_sb({"default_provider": "claude"})
        with patch("database.models.get_sb", return_value=sb), \
             patch("database.models._ensure_user_preferences_row"):
            result = models.get_default_provider_for_user("user-1")
        assert result == "claude"

    def test_set_default_provider_normalizes_invalid_to_cursor(self):
        sb = self._prefs_sb({})
        with patch("database.models.get_sb", return_value=sb), \
             patch("database.models._ensure_user_preferences_row"):
            models.set_default_provider_for_user("user-1", "BADVALUE")
        update_payload = sb.table.return_value.update.call_args[0][0]
        assert update_payload["default_provider"] == "cursor"

    def test_get_terminal_access_returns_false_by_default(self):
        sb = self._prefs_sb({})
        with patch("database.models.get_sb", return_value=sb), \
             patch("database.models._ensure_user_preferences_row"):
            result = models.get_terminal_access_for_user("user-1")
        assert result is False

    def test_get_terminal_access_returns_true_when_granted(self):
        sb = self._prefs_sb({"terminal_access_granted": True})
        with patch("database.models.get_sb", return_value=sb), \
             patch("database.models._ensure_user_preferences_row"):
            result = models.get_terminal_access_for_user("user-1")
        assert result is True


# ---------------------------------------------------------------------------
# Terminal command operations
# ---------------------------------------------------------------------------

class TestTerminalCommandOperations:
    def test_complete_terminal_command_updates_status(self):
        sb = _mock_sb()
        with patch("database.models.get_sb", return_value=sb):
            models.complete_terminal_command(command_id="cmd-1", status="success", exit_code=0)
        payload = sb.table.return_value.update.call_args[0][0]
        assert payload["status"] == "success"
        assert payload["exit_code"] == 0

    def test_complete_terminal_command_sets_completed_at(self):
        sb = _mock_sb()
        with patch("database.models.get_sb", return_value=sb):
            models.complete_terminal_command(command_id="cmd-1", status="failed")
        payload = sb.table.return_value.update.call_args[0][0]
        assert "completed_at" in payload

    def test_update_call_session_sets_ended_at(self):
        sb = _mock_sb()
        with patch("database.models.get_sb", return_value=sb):
            models.update_call_session("sess-1", "transcript text", ["cmd1"])
        payload = sb.table.return_value.update.call_args[0][0]
        assert "ended_at" in payload
        assert payload["transcript"] == "transcript text"

    def test_get_user_call_history_returns_list(self):
        fake = [{"id": "s1"}, {"id": "s2"}]
        sb = _mock_sb(fake)
        with patch("database.models.get_sb", return_value=sb):
            result = models.get_user_call_history("user-1")
        assert len(result) == 2
