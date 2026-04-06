"""
Integration tests for core API endpoints.

Strategy
--------
* Set DEVELOPMENT_MODE=true so get_current_user() returns the built-in
  MockUser (id="test-user-123") without requiring Supabase credentials.
* Patch `database.supabase_client.get_sb` (via the `test_db` conftest fixture)
  so all model calls go to an in-memory MagicMock rather than the real DB.
* Always use user_id="test-user-123" in URL paths / request bodies so the
  `_require_user_match` authorization check passes.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Enable dev-mode mock user BEFORE importing main so get_current_user sees it
os.environ.setdefault("DEVELOPMENT_MODE", "true")
# Ensure Telegram webhook tests run in dev mode even when a local .env defines a secret.
os.environ["TELEGRAM_SECRET_TOKEN"] = ""

from main import app  # noqa: E402

# Auth user id that the dev-mode MockUser returns
TEST_USER_ID = "test-user-123"


@pytest.fixture(autouse=True)
def clear_supabase_singleton():
    """Reset the Supabase client singleton between tests."""
    import database.supabase_client as sbc
    old_client = sbc._client
    sbc._client = None
    yield
    sbc._client = old_client


client = TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoints:

    def test_root_returns_status(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "status" in response.json()

    def test_health_returns_ok(self):
        """The root `/` endpoint is effectively the health check."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestProjectsAPI:

    def test_create_project(self, test_db):
        with patch("database.models.upsert_user"), \
             patch("database.models.create_project", return_value="proj-abc") as mock_create:
            response = client.post("/api/projects", json={
                "user_id": TEST_USER_ID,
                "name": "Test Project"
            })
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["project_id"] == "proj-abc"
        mock_create.assert_called_once()

    def test_get_user_projects_empty(self, test_db):
        with patch("database.models.get_user_projects", return_value=[]):
            response = client.get(f"/api/projects/{TEST_USER_ID}")
        assert response.status_code == 200
        assert response.json()["projects"] == []

    def test_get_user_projects_after_create(self, test_db):
        fake_projects = [{"id": "proj-1", "name": "My App", "user_id": TEST_USER_ID}]
        with patch("database.models.get_user_projects", return_value=fake_projects):
            response = client.get(f"/api/projects/{TEST_USER_ID}")
        assert response.status_code == 200
        assert len(response.json()["projects"]) == 1
        assert response.json()["projects"][0]["name"] == "My App"


class TestDashboardAPI:

    def test_dashboard_returns_projects_and_tasks(self, test_db):
        with patch("database.models.get_user_projects_with_task_counts", return_value=[]), \
             patch("database.models.get_user_tasks", return_value=[]):
            response = client.get(f"/api/dashboard/{TEST_USER_ID}")
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert "tasks" in data

    def test_dashboard_empty_for_new_user(self, test_db):
        with patch("database.models.get_user_projects_with_task_counts", return_value=[]), \
             patch("database.models.get_user_tasks", return_value=[]):
            response = client.get(f"/api/dashboard/{TEST_USER_ID}")
        assert response.status_code == 200
        assert response.json()["projects"] == []
        assert response.json()["tasks"] == []


class TestTelegramWebhookAPI:
    """Smoke tests for the Telegram webhook endpoint (no Supabase required)."""

    def test_webhook_ignored_no_message(self):
        """Payloads without a message key should be silently ignored."""
        response = client.post("/api/telegram/webhook", json={"update_id": 99}, headers={"X-Telegram-Bot-Api-Secret-Token": ""})
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    def test_webhook_ignored_empty_text(self):
        """Payloads with empty text should be silently ignored."""
        payload = {
            "update_id": 1,
            "message": {"chat": {"id": 123}, "text": ""}
        }
        response = client.post("/api/telegram/webhook", json=payload, headers={"X-Telegram-Bot-Api-Secret-Token": ""})
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    def test_webhook_new_user_gets_welcome(self):
        """A chat_id not seen before should trigger user creation + welcome message."""
        with patch("main.models.get_user_id_by_telegram_chat_id", return_value=None), \
             patch("main.models.upsert_user") as mock_upsert, \
             patch("main.send_telegram_message") as mock_send:

            mock_send.return_value = None  # silence actual HTTP call

            payload = {
                "update_id": 2,
                "message": {"chat": {"id": 777999}, "text": "hello bot"}
            }
            response = client.post("/api/telegram/webhook", json=payload, headers={"X-Telegram-Bot-Api-Secret-Token": ""})

        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["action"] == "user_created"
        mock_upsert.assert_called_once()
        assert mock_send.call_count >= 1
        # Welcome message should be sent back to the right chat
        first_call = mock_send.call_args_list[0]
        assert first_call.args[0] == 777999