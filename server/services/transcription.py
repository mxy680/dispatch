# server/services/transcription.py
"""Speech-to-text via Groq's Whisper API (replaces local faster-whisper)."""

import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger("dispatch.transcription")

_client: AsyncOpenAI | None = None


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
    """
    model = os.environ.get("GROQ_WHISPER_MODEL", "whisper-large-v3")
    client = _get_client()
    with open(file_path, "rb") as audio_file:
        response = await client.audio.transcriptions.create(
            model=model,
            file=audio_file,
        )
    return response.text.strip()
