"""
Unit tests for database model functions.

These tests mock `database.models.get_sb` (the bound name inside models.py)
so no real Supabase connection is needed.
"""
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
    c.maybe_single.return_value = c
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
