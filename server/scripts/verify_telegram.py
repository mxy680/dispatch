import os
import asyncio
import httpx
from dotenv import load_dotenv

# Load .env from the parent directory (server/.env)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

async def verify_connection(chat_id: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not found in environment.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "✅ *Dispatch Telegram Integration* is working!\n\nThis is a test message from your server.",
        "parse_mode": "Markdown"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            print(f"Success! Message sent to chat_id: {chat_id}")
        except Exception as e:
            print(f"Failed to send message: {e}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python verify_telegram.py <CHAT_ID>")
        sys.exit(1)
    
    chat_id = sys.argv[1]
    asyncio.run(verify_connection(chat_id))
