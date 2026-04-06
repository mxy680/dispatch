import os
import asyncio
import httpx
from dotenv import load_dotenv

# Load .env from the parent directory (server/.env)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

async def set_webhook(webhook_url: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    secret_token = os.environ.get("TELEGRAM_SECRET_TOKEN")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not found in environment.")
        return

    url = f"https://api.telegram.org/bot{token}/setWebhook"
    payload = {
        "url": webhook_url,
        "allowed_updates": ["message"],
    }
    if secret_token:
        payload["secret_token"] = secret_token
        print(f"Using secret token for security.")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            print(f"Success! Webhook set to: {webhook_url}")
            print(f"Response: {response.json()}")
        except httpx.HTTPStatusError as e:
            print(f"Telegram API error {e.response.status_code}: {e.response.text}")
        except Exception as e:
            print(f"Unexpected error: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python set_webhook.py <WEBHOOK_URL>")
        print("Example: python set_webhook.py https://your-domain.ngrok.io/api/telegram/webhook")
        sys.exit(1)
    
    webhook_url = sys.argv[1]
    asyncio.run(set_webhook(webhook_url))
