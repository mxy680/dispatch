from database import models


class TestProjects:
    def test_create_project(self, test_db):
        pid = models.create_project("user-1", "My App")
        assert pid is not None

        project = models.get_project_by_id(pid)
        assert project["name"] == "My App"
        assert project["user_id"] == "user-1"

    def test_get_user_projects(self, test_db):
        models.create_project("user-1", "Project A")
        models.create_project("user-1", "Project B")
        models.create_project("user-2", "Project C")

        projects = models.get_user_projects("user-1")
        assert len(projects) == 2
        names = {p["name"] for p in projects}
        assert names == {"Project A", "Project B"}

    def test_get_project_by_name_case_insensitive(self, test_db):
        models.create_project("user-1", "My Website")

        assert models.get_project_by_name("user-1", "My Website") is not None
        assert models.get_project_by_name("user-1", "my website") is not None
        assert models.get_project_by_name("user-1", "MY WEBSITE") is not None
        assert models.get_project_by_name("user-1", "nonexistent") is None

    def test_get_project_by_name_scoped_to_user(self, test_db):
        models.create_project("user-1", "Shared Name")
        models.create_project("user-2", "Shared Name")

        result = models.get_project_by_name("user-1", "Shared Name")
        assert result["user_id"] == "user-1"


class TestTasks:
    def test_create_task(self, test_db):
        pid = models.create_project("user-1", "App")
        models.create_task(pid, "Fix bug")

        tasks = models.get_project_tasks(pid)
        assert len(tasks) == 1
        assert tasks[0]["description"] == "Fix bug"
        assert tasks[0]["voice_command"] is None

    def test_create_task_with_voice_command(self, test_db):
        pid = models.create_project("user-1", "App")
        models.create_task(pid, "Fix bug", voice_command="fix the bug on my app")

        tasks = models.get_project_tasks(pid)
        assert tasks[0]["voice_command"] == "fix the bug on my app"

    def test_update_task_status(self, test_db):
        pid = models.create_project("user-1", "App")
        tid = models.create_task(pid, "Fix bug")

        models.update_task_status(tid, "completed")
        tasks = models.get_project_tasks(pid)
        assert tasks[0]["status"] == "completed"
        assert tasks[0]["completed_at"] is not None

    def test_get_user_projects_with_task_counts(self, test_db):
        pid = models.create_project("user-1", "App")
        models.create_task(pid, "Task 1")
        models.create_task(pid, "Task 2")
        tid3 = models.create_task(pid, "Task 3")
        models.update_task_status(tid3, "completed")

        results = models.get_user_projects_with_task_counts("user-1")
        assert len(results) == 1
        assert results[0]["total_tasks"] == 3
        assert results[0]["pending_tasks"] == 2
        assert results[0]["completed_tasks"] == 1

    def test_projects_with_no_tasks(self, test_db):
        models.create_project("user-1", "Empty Project")

        results = models.get_user_projects_with_task_counts("user-1")
        assert len(results) == 1
        assert results[0]["total_tasks"] == 0


class TestCallSessions:
    def test_create_and_update_session(self, test_db):
        sid = models.create_call_session("user-1", "+15551234567")
        assert sid is not None

        models.update_call_session(sid, "hello world", '["task-1"]')

        history = models.get_user_call_history("user-1")
        assert len(history) == 1
        assert history[0]["transcript"] == "hello world"
        assert history[0]["ended_at"] is not None
