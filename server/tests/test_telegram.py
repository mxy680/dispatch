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
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token_123"}):
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

def test_telegram_webhook_ignored_no_message():
    """Test webhook ignores payloads without message object."""
    response = client.post("/api/telegram/webhook", json={"update_id": 1})
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"

def test_telegram_webhook_ignored_empty_text():
    """Test webhook ignores payloads with empty text."""
    payload = {
        "update_id": 1,
        "message": {
            "chat": {"id": 123},
            "text": ""
        }
    }
    response = client.post("/api/telegram/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"

@patch("main.send_telegram_message", new_callable=AsyncMock)
@patch("main.models.get_user_id_by_telegram_chat_id")
@patch("main.models.upsert_user")
def test_telegram_webhook_new_user(mock_upsert, mock_get_user, mock_send):
    """Test that a new user is created and welcomed if the chat_id is unknown."""
    # Simulate DB not finding the user
    mock_get_user.return_value = None
    
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
    assert response.json()["action"] == "user_created"
    
    # Verify user was upserted with pseudo ID
    mock_upsert.assert_called_once()
    args, kwargs = mock_upsert.call_args
    assert kwargs["telegram_chat_id"] == "999111"
    
    # Verify welcome message was sent
    mock_send.assert_called_once()
    args, kwargs = mock_send.call_args
    assert args[0] == 999111
    assert "Welcome to Dispatch" in args[1]
