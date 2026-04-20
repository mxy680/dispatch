# server/services/transcription.py
"""Speech-to-text via Groq's Whisper API (replaces local faster-whisper)."""

import logging
import os
from typing import Optional

from openai import AsyncOpenAI, APIConnectionError, APIStatusError, APITimeoutError

logger = logging.getLogger("dispatch.transcription")

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        _client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )
    return _client


async def transcribe_file(file_path: str) -> str:
    """Transcribe an audio file using Groq's Whisper API.

    Args:
        file_path: Path to the audio file (mp3, wav, etc.)

    Returns:
        Transcribed text string.

    Raises:
        RuntimeError: If the Groq API is unavailable or returns an error.
    """
    model = os.environ.get("GROQ_WHISPER_MODEL", "whisper-large-v3")
    try:
        client = _get_client()
    except RuntimeError:
        raise RuntimeError("Speech-to-text unavailable: GROQ_API_KEY is not configured.")

    try:
        with open(file_path, "rb") as audio_file:
            response = await client.audio.transcriptions.create(
                model=model,
                file=audio_file,
            )
        return response.text.strip()
    except APITimeoutError:
        logger.error("Groq Whisper API timed out for file: %s", file_path)
        raise RuntimeError("Speech-to-text unavailable: request timed out. Please try again.")
    except APIConnectionError as e:
        logger.error("Groq Whisper API connection error: %s", e)
        raise RuntimeError("Speech-to-text unavailable: could not reach the Groq API. Please try again.")
    except APIStatusError as e:
        logger.error("Groq Whisper API status error %s: %s", e.status_code, e.message)
        if e.status_code == 429:
            raise RuntimeError("Speech-to-text unavailable: rate limit reached. Please wait a moment and try again.")
        raise RuntimeError(f"Speech-to-text unavailable: service returned an error ({e.status_code}).")
    except Exception as e:
        logger.error("Unexpected transcription error: %s", e)
        raise RuntimeError("Speech-to-text unavailable: an unexpected error occurred. Please use text input instead.")
