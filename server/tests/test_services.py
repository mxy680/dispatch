"""
Tests for services/telegram.py and services/transcription.py.

All external HTTP and API calls are mocked.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# services/telegram.py
# ---------------------------------------------------------------------------

class TestGetToken:
    def test_returns_token_when_set(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-123")
        from services.telegram import get_token
        assert get_token() == "test-token-123"

    def test_raises_when_not_set(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        from services.telegram import get_token
        with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN not set"):
            get_token()


class TestVerifySecretToken:
    def test_returns_true_when_no_secret_configured(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_SECRET_TOKEN", raising=False)
        from services.telegram import verify_secret_token
        assert verify_secret_token("anything") is True

    def test_returns_true_when_token_matches(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_SECRET_TOKEN", "my-secret")
        from services.telegram import verify_secret_token
        assert verify_secret_token("my-secret") is True

    def test_returns_false_when_token_mismatch(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_SECRET_TOKEN", "my-secret")
        from services.telegram import verify_secret_token
        assert verify_secret_token("wrong-token") is False

    def test_returns_false_when_none_and_secret_configured(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_SECRET_TOKEN", "my-secret")
        from services.telegram import verify_secret_token
        assert verify_secret_token(None) is False


class TestSendTelegramMessage:
    async def test_returns_true_on_success(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.telegram.httpx.AsyncClient", return_value=mock_client):
            from services.telegram import send_telegram_message
            result = await send_telegram_message(12345, "Hello!")
        assert result is True

    async def test_returns_false_on_http_error(self, monkeypatch):
        import httpx
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("error", request=MagicMock(), response=mock_response)
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.telegram.httpx.AsyncClient", return_value=mock_client):
            from services.telegram import send_telegram_message
            result = await send_telegram_message(12345, "Hello!")
        assert result is False

    async def test_returns_false_on_generic_exception(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.telegram.httpx.AsyncClient", return_value=mock_client):
            from services.telegram import send_telegram_message
            result = await send_telegram_message(12345, "Hello!")
        assert result is False

    async def test_send_typing_action_swallows_errors(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.telegram.httpx.AsyncClient", return_value=mock_client):
            from services.telegram import send_typing_action
            # Should not raise
            await send_typing_action(12345)


# ---------------------------------------------------------------------------
# services/transcription.py
# ---------------------------------------------------------------------------

class TestTranscription:
    def test_get_client_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        import services.transcription as t
        t._client = None  # reset cached client
        with pytest.raises(RuntimeError, match="GROQ_API_KEY is not set"):
            t._get_client()

    def test_get_client_returns_client_with_api_key(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        import services.transcription as t
        t._client = None
        with patch("services.transcription.AsyncOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            client = t._get_client()
        assert client is not None
        t._client = None  # reset after test

    async def test_transcribe_file_returns_text(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        import services.transcription as t

        # Create a dummy audio file
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"fake audio data")

        mock_response = MagicMock()
        mock_response.text = "  Hello world  "

        mock_transcriptions = AsyncMock()
        mock_transcriptions.create = AsyncMock(return_value=mock_response)

        mock_client = MagicMock()
        mock_client.audio.transcriptions = mock_transcriptions

        t._client = mock_client
        result = await t.transcribe_file(str(audio))
        assert result == "Hello world"
        t._client = None
