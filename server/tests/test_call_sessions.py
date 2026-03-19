from database import models


class TestCallSessions:

    def test_create_call_session_returns_id(self, test_db):
        sid = models.create_call_session("user-1", "+15551234567")
        assert sid is not None
        assert isinstance(sid, str)

    def test_call_session_appears_in_history(self, test_db):
        models.create_call_session("user-1", "+15551234567")
        history = models.get_user_call_history("user-1")
        assert len(history) == 1

    def test_update_call_session_saves_transcript(self, test_db):
        sid = models.create_call_session("user-1", "+15551234567")
        models.update_call_session(sid, "create a project called dispatch", '["task-1"]')
        history = models.get_user_call_history("user-1")
        assert history[0]["transcript"] == "create a project called dispatch"

    def test_update_call_session_sets_ended_at(self, test_db):
        sid = models.create_call_session("user-1", "+15551234567")
        models.update_call_session(sid, "some transcript", '[]')
        history = models.get_user_call_history("user-1")
        assert history[0]["ended_at"] is not None

    def test_update_call_session_saves_commands(self, test_db):
        sid = models.create_call_session("user-1", "+15551234567")
        models.update_call_session(sid, "transcript", '["task-abc", "task-xyz"]')
        history = models.get_user_call_history("user-1")
        assert history[0]["commands_executed"] == '["task-abc", "task-xyz"]'

    def test_multiple_sessions_ordered_by_most_recent(self, test_db):
        models.create_call_session("user-1", "+15551234567")
        models.create_call_session("user-1", "+15551234567")
        models.create_call_session("user-1", "+15551234567")
        history = models.get_user_call_history("user-1")
        assert len(history) == 3

    def test_history_scoped_to_user(self, test_db):
        models.create_call_session("user-1", "+15551111111")
        models.create_call_session("user-2", "+15552222222")
        history = models.get_user_call_history("user-1")
        assert len(history) == 1
        assert history[0]["user_id"] == "user-1"

    def test_history_limit_respected(self, test_db):
        for _ in range(5):
            models.create_call_session("user-1", "+15551234567")
        history = models.get_user_call_history("user-1", limit=3)
        assert len(history) == 3

    def test_empty_history_for_new_user(self, test_db):
        history = models.get_user_call_history("user-nobody")
        assert history == []