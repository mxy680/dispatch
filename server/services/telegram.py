import os
import httpx
import logging

logger = logging.getLogger("callstack.telegram")

async def send_telegram_message(chat_id: int | str, text: str):
    """Sends a message back to the user via Telegram API."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return False
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return True
    except Exception as e:
        logger.error("Failed to send telegram message to %s: %r", chat_id, e)
        return False
