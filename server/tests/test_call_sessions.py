"""
Unit tests for call-session model functions.

Patch `database.models.get_sb` (the bound name inside models.py)
so no real Supabase connection is needed.
"""
from unittest.mock import patch, MagicMock
from database import models


def _chain(data):
    result = MagicMock()
    result.data = data
    c = MagicMock()
    c.execute.return_value = result
    c.eq.return_value = c
    c.order.return_value = c
    c.limit.return_value = c
    c.select.return_value = c
    c.insert.return_value = c
    c.update.return_value = c
    c.maybe_single.return_value = c
    return c


def _mock_sb(data):
    sb = MagicMock()
    sb.table.return_value = _chain(data)
    return sb


class TestCallSessions:

    def test_create_call_session_returns_id(self):
        """create_call_session should insert a row and return its id."""
        fake_row = {"id": "session-001", "user_id": "user-1"}
        with patch("database.models.get_sb", return_value=_mock_sb([fake_row])):
            sid = models.create_call_session("user-1", "+15551234567")
        assert sid is not None

    def test_create_call_session_returns_str(self):
        """The session id returned should be a string."""
        fake_row = {"id": "abc-123", "user_id": "user-1"}
        with patch("database.models.get_sb", return_value=_mock_sb([fake_row])):
            sid = models.create_call_session("user-1", "+15551234567")
        assert isinstance(sid, str)

    def test_get_user_call_history_returns_list(self):
        """get_user_call_history should return a list of session dicts."""
        fake_sessions = [
            {"id": "s1", "user_id": "user-1", "transcript": "hello"},
            {"id": "s2", "user_id": "user-1", "transcript": "world"},
        ]
        with patch("database.models.get_sb", return_value=_mock_sb(fake_sessions)):
            history = models.get_user_call_history("user-1")
        assert len(history) == 2

    def test_get_user_call_history_empty(self):
        """A user with no sessions should get an empty list."""
        with patch("database.models.get_sb", return_value=_mock_sb([])):
            history = models.get_user_call_history("user-nobody")
        assert history == []

    def test_update_call_session_calls_supabase(self):
        """update_call_session should call supabase update without raising."""
        sb = _mock_sb([{"id": "s1"}])
        with patch("database.models.get_sb", return_value=sb):
            models.update_call_session("s1", "transcript text", '["task-1"]')
        sb.table.assert_called()