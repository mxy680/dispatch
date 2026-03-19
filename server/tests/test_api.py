from __future__ import annotations
import pytest
import sys
from unittest.mock import MagicMock

# Mock missing modules before importing app
sys.modules["agents"] = MagicMock()
sys.modules["agents.copilot_agent"] = MagicMock()

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestHealthEndpoints:

    def test_root_returns_status(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "status" in response.json()

    def test_health_returns_healthy(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestProjectsAPI:

    def test_create_project(self, test_db):
        response = client.post("/api/projects", json={
            "user_id": "test-user-123",
            "name": "Test Project"
        })
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert "project_id" in response.json()

    def test_get_user_projects_empty(self, test_db):
        response = client.get("/api/projects/nonexistent-user")
        assert response.status_code == 200
        assert response.json()["projects"] == []

    def test_get_user_projects_after_create(self, test_db):
        client.post("/api/projects", json={
            "user_id": "test-user-123",
            "name": "My App"
        })
        response = client.get("/api/projects/test-user-123")
        assert response.status_code == 200
        assert len(response.json()["projects"]) == 1
        assert response.json()["projects"][0]["name"] == "My App"


class TestCallSessionsAPI:

    def test_get_call_history_empty(self, test_db):
        response = client.get("/api/call-sessions/nonexistent-user")
        assert response.status_code == 200
        assert response.json()["sessions"] == []

    def test_get_call_history_returns_sessions(self, test_db):
        from database import models
        sid = models.create_call_session("test-user-123", "+15551234567")
        models.update_call_session(sid, "create a project", '[]')

        response = client.get("/api/call-sessions/test-user-123")
        assert response.status_code == 200
        sessions = response.json()["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["transcript"] == "create a project"

    def test_get_call_history_scoped_to_user(self, test_db):
        from database import models
        models.create_call_session("user-a", "+15551111111")
        models.create_call_session("user-b", "+15552222222")

        response = client.get("/api/call-sessions/user-a")
        assert response.status_code == 200
        assert len(response.json()["sessions"]) == 1


class TestDashboardAPI:

    def test_dashboard_returns_projects_and_tasks(self, test_db):
        response = client.get("/api/dashboard/test-user-123")
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert "tasks" in data

    def test_dashboard_empty_for_new_user(self, test_db):
        response = client.get("/api/dashboard/brand-new-user")
        assert response.status_code == 200
        assert response.json()["projects"] == []
        assert response.json()["tasks"] == []