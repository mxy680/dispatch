import os
import logging
import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def get_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    return token


def verify_secret_token(incoming: str | None) -> bool:
    """Validate the X-Telegram-Bot-Api-Secret-Token header."""
    expected = os.environ.get("TELEGRAM_SECRET_TOKEN", "")
    if not expected:
        return True  # No secret configured → skip check (dev mode)
    return incoming == expected


async def send_telegram_message(chat_id: int, text: str) -> bool:
    """Send a message back to a Telegram user. Returns True on success."""
    try:
        token = get_token()
        url = f"{TELEGRAM_API}/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        logger.error("Telegram API error %s: %s", e.response.status_code, e.response.text)
    except Exception as e:
        logger.error("Failed to send Telegram message: %s", e)
    return False


async def send_typing_action(chat_id: int) -> None:
    """Show 'typing...' indicator while agents are working."""
    try:
        token = get_token()
        url = f"{TELEGRAM_API}/bot{token}/sendChatAction"
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json={"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass  # Non-critical, swallow silently