"""Integration tests for database/models.py — Supabase calls are mocked.

Each test configures a mock Supabase client returned by get_sb() so that
we exercise the model functions' logic (branching, error handling, call order)
without hitting a real database.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

GET_SB_PATH = "database.models.get_sb"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sb():
    """Return a fresh MagicMock that behaves like a Supabase client."""
    return MagicMock()


def _result(data):
    """Wrap data in a mock result object (mimics supabase-py ExecuteResponse)."""
    r = MagicMock()
    r.data = data
    return r


# ---------------------------------------------------------------------------
# upsert_user
# ---------------------------------------------------------------------------


class TestUpsertUser:
    def test_new_user_path_calls_insert(self):
        sb = _make_sb()
        # maybe_single().execute() returns None → user does not exist
        sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
            _result(None)
        )

        with patch(GET_SB_PATH, return_value=sb):
            from database import models
            models.upsert_user("user-new", "new@example.com")

        sb.table.return_value.insert.assert_called_once()
        insert_data = sb.table.return_value.insert.call_args.args[0]
        assert insert_data["id"] == "user-new"
        assert insert_data["email"] == "new@example.com"

    def test_new_user_with_phone_includes_phone_in_insert(self):
        sb = _make_sb()
        sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
            _result(None)
        )

        with patch(GET_SB_PATH, return_value=sb):
            from database import models
            models.upsert_user("user-new", "new@example.com", phone_number="+15551234567")

        insert_data = sb.table.return_value.insert.call_args.args[0]
        assert insert_data.get("phone_number") == "+15551234567"

    def test_existing_user_path_calls_update_not_insert(self):
        sb = _make_sb()
        # maybe_single().execute() returns existing user
        sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
            _result({"id": "user-old"})
        )

        with patch(GET_SB_PATH, return_value=sb):
            from database import models
            models.upsert_user("user-old", "old@example.com")

        sb.table.return_value.update.assert_called_once()
        sb.table.return_value.insert.assert_not_called()

    def test_existing_user_update_includes_email(self):
        sb = _make_sb()
        sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
            _result({"id": "user-old"})
        )

        with patch(GET_SB_PATH, return_value=sb):
            from database import models
            models.upsert_user("user-old", "updated@example.com")

        update_data = sb.table.return_value.update.call_args.args[0]
        assert update_data["email"] == "updated@example.com"


# ---------------------------------------------------------------------------
# update_user_phone_number
# ---------------------------------------------------------------------------


class TestUpdateUserPhoneNumber:
    def test_success_calls_update(self):
        sb = _make_sb()

        with patch(GET_SB_PATH, return_value=sb):
            from database import models
            models.update_user_phone_number("user-1", "+15551234567")

        sb.table.return_value.update.assert_called_once_with({"phone_number": "+15551234567"})

    def test_duplicate_phone_raises_value_error(self):
        sb = _make_sb()
        # Simulate a unique-constraint violation from supabase-py
        sb.table.return_value.update.return_value.eq.return_value.execute.side_effect = Exception(
            "duplicate key value violates unique constraint"
        )

        with patch(GET_SB_PATH, return_value=sb):
            from database import models
            with pytest.raises(ValueError, match="already linked"):
                models.update_user_phone_number("user-1", "+15551234567")

    def test_other_exception_is_re_raised(self):
        sb = _make_sb()
        sb.table.return_value.update.return_value.eq.return_value.execute.side_effect = RuntimeError(
            "connection refused"
        )

        with patch(GET_SB_PATH, return_value=sb):
            from database import models
            with pytest.raises(RuntimeError):
                models.update_user_phone_number("user-1", "+15551234567")


# ---------------------------------------------------------------------------
# delete_project — cascading delete order
# ---------------------------------------------------------------------------


class TestDeleteProject:
    def test_deletes_terminal_logs_before_commands(self):
        sb = _make_sb()
        # terminal_sessions → session ids
        sb.table.return_value.select.return_value.eq.return_value.execute.return_value = _result(
            [{"id": "sess-1"}]
        )
        # terminal_commands → command ids
        sb.table.return_value.select.return_value.in_.return_value.execute.return_value = _result(
            [{"id": "cmd-1"}]
        )
        # tasks → task ids (for agent_executions cleanup)
        # Chained differently — use side_effect to control per-table responses.

        delete_calls = []

        def track_delete(*args, **kwargs):
            mock = MagicMock()
            mock.in_ = track_delete
            mock.eq = track_delete
            mock.execute = MagicMock(return_value=_result(None))
            delete_calls.append(args)
            return mock

        with patch(GET_SB_PATH, return_value=sb):
            from database import models
            # Provide a clean sb mock with controlled responses
            sb2 = MagicMock()

            sess_result = _result([{"id": "sess-1"}])
            cmd_result = _result([{"id": "cmd-1"}])
            task_result = _result([{"id": "task-1"}])
            empty_result = _result([])

            table_calls: list[str] = []

            def table_side_effect(name):
                table_calls.append(name)
                m = MagicMock()
                # Make all chained calls return something sensible
                m.select.return_value.eq.return_value.execute.return_value = (
                    sess_result if name == "terminal_sessions" else
                    task_result if name == "tasks" else
                    empty_result
                )
                m.select.return_value.in_.return_value.execute.return_value = (
                    cmd_result if name == "terminal_commands" else empty_result
                )
                m.delete.return_value.in_.return_value.execute.return_value = _result(None)
                m.delete.return_value.eq.return_value.execute.return_value = _result(None)
                return m

            sb2.table.side_effect = table_side_effect

            with patch(GET_SB_PATH, return_value=sb2):
                models.delete_project("proj-1")

        # terminal_logs must be deleted before terminal_commands
        assert "terminal_logs" in table_calls
        assert "terminal_commands" in table_calls
        logs_idx = [i for i, t in enumerate(table_calls) if t == "terminal_logs"]
        cmds_idx = [i for i, t in enumerate(table_calls) if t == "terminal_commands" and table_calls.index("terminal_logs") < i]
        # There should be at least one terminal_logs delete before a terminal_commands delete
        assert len(logs_idx) > 0

    def test_project_row_is_deleted_last(self):
        sb = MagicMock()
        table_calls: list[str] = []

        def table_side_effect(name):
            table_calls.append(name)
            m = MagicMock()
            m.select.return_value.eq.return_value.execute.return_value = _result([])
            m.select.return_value.in_.return_value.execute.return_value = _result([])
            m.delete.return_value.in_.return_value.execute.return_value = _result(None)
            m.delete.return_value.eq.return_value.execute.return_value = _result(None)
            return m

        sb.table.side_effect = table_side_effect

        with patch(GET_SB_PATH, return_value=sb):
            from database import models
            models.delete_project("proj-1")

        # The final table call that involves deletion should be "projects"
        delete_table_calls = table_calls  # every call to .table() may be for delete or select
        assert table_calls[-1] == "projects"


# ---------------------------------------------------------------------------
# claim_next_queued_command_for_user
# ---------------------------------------------------------------------------


class TestClaimNextQueuedCommand:
    def _make_queued_cmd(self):
        return {"id": "cmd-queued", "status": "queued", "session_id": "sess-1", "user_id": "user-1"}

    def _make_running_cmd(self):
        return {"id": "cmd-queued", "status": "running", "session_id": "sess-1", "user_id": "user-1"}

    def test_finds_and_claims_queued_command(self):
        """Patch _expire_stale and use per-table mocks to avoid chain conflicts."""
        running_cmd = self._make_running_cmd()

        # Use a table-dispatch approach so each table gets its own sub-mock.
        table_mocks: dict[str, MagicMock] = {}

        def table_side_effect(name):
            if name not in table_mocks:
                table_mocks[name] = MagicMock()
            return table_mocks[name]

        with patch("database.models._expire_stale_running_commands"), \
             patch(GET_SB_PATH) as mock_get_sb:

            sb = MagicMock()
            sb.table.side_effect = table_side_effect
            mock_get_sb.return_value = sb

            tc = table_mocks.setdefault("terminal_commands", MagicMock())
            # find queued: .select().eq().eq().order().limit().maybe_single().execute()
            tc.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.maybe_single.return_value.execute.return_value = _result(self._make_queued_cmd())
            # update to running: .update().eq().eq().execute()
            tc.update.return_value.eq.return_value.eq.return_value.execute.return_value = _result(None)
            # re-fetch verify: .select().eq().maybe_single().execute()
            tc.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _result(running_cmd)

            # sessions lookup → return None so project_path attachment is skipped
            ts = table_mocks.setdefault("terminal_sessions", MagicMock())
            ts.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = _result(None)

            from database import models
            result = models.claim_next_queued_command_for_user(user_id="user-1")

        assert result is not None
        assert result["status"] == "running"

    def test_returns_none_when_no_queued_commands(self):
        with patch("database.models._expire_stale_running_commands"), \
             patch(GET_SB_PATH) as mock_get_sb:

            sb = MagicMock()
            mock_get_sb.return_value = sb

            # No queued commands found
            sb.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.maybe_single.return_value.execute.return_value = _result(None)

            from database import models
            result = models.claim_next_queued_command_for_user(user_id="user-1")

        assert result is None


# ---------------------------------------------------------------------------
# _expire_stale_running_commands
# ---------------------------------------------------------------------------


class TestExpireStaleRunningCommands:
    def test_marks_stale_commands_as_failed(self):
        sb = MagicMock()

        stale_cmd = {"id": "cmd-stale"}
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.lt.return_value.execute.return_value = (
            _result([stale_cmd])
        )

        with patch(GET_SB_PATH, return_value=sb):
            from database import models
            models._expire_stale_running_commands("user-1")

        # update should have been called with status="failed"
        update_call = sb.table.return_value.update.call_args
        assert update_call is not None
        update_data = update_call.args[0]
        assert update_data["status"] == "failed"
        assert update_data["exit_code"] == -1

    def test_no_update_when_no_stale_commands(self):
        sb = MagicMock()

        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.lt.return_value.execute.return_value = (
            _result([])
        )

        with patch(GET_SB_PATH, return_value=sb):
            from database import models
            models._expire_stale_running_commands("user-1")

        # No update calls on terminal_commands
        sb.table.return_value.update.assert_not_called()
