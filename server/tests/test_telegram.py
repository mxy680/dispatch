import pytest
import os
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from main import app
from services import telegram
from database import models

client = TestClient(app)

@pytest.fixture
def mock_telegram_env():
    # Patch both tokens to ensure the real .env doesn't interfere
    with patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "test_token_123",
        "TELEGRAM_SECRET_TOKEN": ""
    }):
        yield

@pytest.fixture
def mock_telegram_env_with_secret():
    with patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "test_token_123",
        "TELEGRAM_SECRET_TOKEN": "secret_123"
    }):
        yield

@pytest.mark.asyncio
async def test_send_telegram_message(mock_telegram_env):
    """Test that send_telegram_message makes the correct HTTPX call."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.raise_for_status = AsyncMock()
        
        result = await telegram.send_telegram_message(123456789, "Hello World")
        
        assert result is True
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["chat_id"] == 123456789
        assert kwargs["json"]["text"] == "Hello World"
        assert kwargs["json"]["parse_mode"] == "HTML"
        assert "bottest_token_123" in args[0]

def test_telegram_webhook_ignored_no_message(mock_telegram_env):
    """Test webhook ignores payloads without message object."""
    response = client.post("/api/telegram/webhook", json={"update_id": 1})
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"

def test_telegram_webhook_unauthorized(mock_telegram_env_with_secret):
    """Test webhook rejects requests with invalid secret token."""
    payload = {"update_id": 1, "message": {"chat": {"id": 123}, "text": "hello"}}
    response = client.post(
        "/api/telegram/webhook", 
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "unauthorized"

@patch("main.send_telegram_message", new_callable=AsyncMock)
@patch("main.models.get_user_id_by_telegram_chat_id")
@patch("main.models.upsert_user")
@patch("main.models.get_user_projects")
@patch("main.parse_intent")
@patch("main.models.log_agent_event_task")
@patch("main.models.get_terminal_access_for_user")
def test_telegram_webhook_new_user(mock_terminal, mock_log, mock_intent, mock_projects, mock_upsert, mock_get_user, mock_send, mock_telegram_env):
    """Test that a new user is created and welcomed, and processing continues."""
    # Simulate DB and LLM behavior
    mock_get_user.return_value = None
    mock_projects.return_value = []
    mock_intent.return_value = {"intent": "unknown"}
    mock_terminal.return_value = False
    
    payload = {
        "update_id": 1,
        "message": {
            "chat": {"id": 999111},
            "text": "Hello bot"
        }
    }
    
    response = client.post("/api/telegram/webhook", json=payload)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["processed"] is True
    
    # Verify user was upserted with pseudo ID
    mock_upsert.assert_called_once()
    
    # Verify welcome message was sent
    mock_send.assert_any_call(999111, "Welcome to Dispatch! I've created a new account for you. Processing your command now...")
