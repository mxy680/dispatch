import os
import sys
from dotenv import load_dotenv

# Add parent directory to path to import database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load environment first
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database import models

def grant_access(identifier: str):
    """Grant terminal access to a user by ID or Telegram Chat ID."""
    # Try by user_id first
    user_id = identifier
    
    # Try by telegram_chat_id if it looks like a chat ID or start with 'tg_'
    if identifier.isdigit() or identifier.startswith("tg_"):
        tg_id = identifier.replace("tg_", "")
        found_id = models.get_user_id_by_telegram_chat_id(tg_id)
        if found_id:
            user_id = found_id
            print(f"Found user_id={user_id} for Telegram Chat ID {tg_id}")

    try:
        models.set_terminal_access_for_user(user_id, True)
        print(f"✅ Terminal access GRANTED for user: {user_id}")
    except Exception as e:
        print(f"❌ Failed to grant access: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python grant_terminal_access.py <USER_ID_OR_TG_CHAT_ID>")
        sys.exit(1)
    
    grant_access(sys.argv[1])
