import os
import sys
import json
import httpx
import asyncio
from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

async def mock_webhook(text: str, chat_id: int | str = 12345678):
    secret_token = os.environ.get("TELEGRAM_SECRET_TOKEN")
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    webhook_url = f"{backend_url}/api/telegram/webhook"
    
    payload = {
        "message": {
            "chat": {
                "id": chat_id,
                "first_name": "Test",
                "last_name": "User",
                "type": "private"
            },
            "text": text,
            "date": 1620000000
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    if secret_token:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret_token
        print(f"Using secret token for security.")

    async with httpx.AsyncClient() as client:
        try:
            print(f"Sending mock message: '{text}' to {webhook_url}")
            response = await client.post(webhook_url, json=payload, headers=headers)
            response.raise_for_status()
            print(f"✅ Success! Response: {response.json()}")
        except Exception as e:
            print(f"❌ Failed to send mock webhook: {e}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python mock_telegram_webhook.py <TEXT_COMMAND> [CHAT_ID]")
        sys.exit(1)
    
    text = sys.argv[1]
    chat_id = sys.argv[2] if len(sys.argv) > 2 else 12345678
    asyncio.run(mock_webhook(text, chat_id))
