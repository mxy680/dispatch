import pytest
import asyncio
import os
from unittest.mock import patch, AsyncMock, MagicMock

# ── Must mock heavy imports BEFORE main loads ──────────────────────────────────
with patch.dict(os.environ, {
    "TELEGRAM_BOT_TOKEN": "test_token_123",
    "TELEGRAM_SECRET_TOKEN": "",
    "SUPABASE_URL": "https://fake.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "fake_key",
    "DEVELOPMENT_MODE": "true",
}):
    with patch("supabase.create_client", return_value=MagicMock()), \
         patch("services.transcription.transcribe_file", new_callable=AsyncMock), \
         patch("agents.dispatcher.dispatch_task", MagicMock()), \
         patch("agents.dispatcher.set_terminal_access", MagicMock()), \
         patch("agents.dispatcher.get_terminal_access", return_value=False):
        from fastapi.testclient import TestClient
        from main import app

client = TestClient(app, raise_server_exceptions=False)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_telegram_env():
    with patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "test_token_123",
        "TELEGRAM_SECRET_TOKEN": "",
    }):
        yield

@pytest.fixture
def mock_telegram_env_with_secret():
    with patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "test_token_123",
        "TELEGRAM_SECRET_TOKEN": "secret_123",
    }):
        yield


# ── send_telegram_message ──────────────────────────────────────────────────────

def test_send_telegram_message(mock_telegram_env):
    """send_telegram_message makes the correct HTTPX call."""
    from services.telegram import send_telegram_message
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.raise_for_status = MagicMock()
        result = asyncio.run(send_telegram_message(123456789, "Hello World"))

    assert result is True
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert kwargs["json"]["chat_id"] == 123456789
    assert kwargs["json"]["text"] == "Hello World"
    assert kwargs["json"]["parse_mode"] == "HTML"
    assert "bottest_token_123" in args[0]


# ── Ignored payloads ───────────────────────────────────────────────────────────

def test_telegram_webhook_ignored_no_message(mock_telegram_env):
    """Webhook ignores payloads without a message object."""
    response = client.post("/api/telegram/webhook", json={"update_id": 1})
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"

def test_telegram_webhook_ignored_empty_text(mock_telegram_env):
    """Webhook ignores messages with empty text."""
    payload = {"update_id": 1, "message": {"chat": {"id": 123}, "text": ""}}
    response = client.post("/api/telegram/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


# ── Security ───────────────────────────────────────────────────────────────────

def test_telegram_webhook_unauthorized(mock_telegram_env_with_secret):
    """Webhook rejects requests with invalid secret token."""
    payload = {"update_id": 1, "message": {"chat": {"id": 123}, "text": "hello"}}
    response = client.post(
        "/api/telegram/webhook",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "unauthorized"

def test_telegram_webhook_correct_secret_passes(mock_telegram_env_with_secret):
    """Correct secret token allows request through."""
    with patch("database.models.get_user_id_by_telegram_chat_id", return_value="user-1"), \
         patch("database.models.get_user_projects", return_value=[]), \
         patch("main.parse_intent", new_callable=AsyncMock,
               return_value={"intent": "unknown"}), \
         patch("database.models.log_agent_event_task", return_value="task-1"), \
         patch("database.models.get_terminal_access_for_user", return_value=False), \
         patch("main.send_telegram_message", new_callable=AsyncMock, return_value=True):
        response = client.post(
            "/api/telegram/webhook",
            json={"update_id": 1, "message": {"chat": {"id": 123}, "text": "hello"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret_123"},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


# ── New user flow ──────────────────────────────────────────────────────────────

def test_telegram_webhook_new_user(mock_telegram_env):
    """New chat_id creates a pseudo user, sends welcome, and continues processing."""
    with patch("database.models.get_user_id_by_telegram_chat_id", return_value=None) as mock_get_user, \
         patch("database.models.upsert_user") as mock_upsert, \
         patch("main.send_telegram_message", new_callable=AsyncMock) as mock_send, \
         patch("database.models.get_user_projects", return_value=[]), \
         patch("main.parse_intent", new_callable=AsyncMock,
               return_value={"intent": "unknown"}), \
         patch("database.models.log_agent_event_task", return_value="task-1"), \
         patch("database.models.get_terminal_access_for_user", return_value=False):
        response = client.post(
            "/api/telegram/webhook",
            json={"update_id": 1, "message": {"chat": {"id": 999111}, "text": "Hello bot"}},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["processed"] is True
    mock_get_user.assert_called_once_with(999111)
    mock_upsert.assert_called_once()
    mock_send.assert_any_call(
        999111,
        "Welcome to Dispatch! I've created a new account for you. Processing your command now..."
    )


# ── Intent routing ─────────────────────────────────────────────────────────────

def test_telegram_webhook_create_project(mock_telegram_env):
    """create_project intent calls create_project and replies with confirmation."""
    with patch("database.models.get_user_id_by_telegram_chat_id", return_value="user-1"), \
         patch("database.models.get_user_projects", return_value=[]), \
         patch("main.parse_intent", new_callable=AsyncMock,
               return_value={"intent": "create_project", "project_name": "my-app"}), \
         patch("database.models.create_project", return_value="proj-1") as mock_create, \
         patch("database.models.log_agent_event_task", return_value="task-1"), \
         patch("database.models.get_terminal_access_for_user", return_value=False), \
         patch("main.send_telegram_message", new_callable=AsyncMock) as mock_send:
        response = client.post(
            "/api/telegram/webhook",
            json={"update_id": 1, "message": {"chat": {"id": 123}, "text": "create project my-app"}},
        )

    assert response.json()["status"] == "success"
    mock_create.assert_called_once_with("user-1", "my-app")
    assert "my-app" in mock_send.call_args[0][1]


# ── Regression: DB failure ─────────────────────────────────────────────────────

def test_telegram_webhook_db_failure_returns_error(mock_telegram_env):
    """If the DB throws, webhook returns error status without crashing the server."""
    with patch("database.models.get_user_id_by_telegram_chat_id",
               side_effect=Exception("DB connection lost")):
        response = client.post(
            "/api/telegram/webhook",
            json={"update_id": 1, "message": {"chat": {"id": 123}, "text": "hello"}},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "error"