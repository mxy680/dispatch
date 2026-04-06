import os
import sys
import argparse
from dotenv import load_dotenv

# Ensure we can import from the database folder
sys.path.append(os.path.abspath(os.path.join(os.getcwd())))

# Load environment variables
load_dotenv(os.path.join(os.getcwd(), ".env"))

def link_account(email, chat_id):
    from database.supabase_client import get_sb
    sb = get_sb()
    
    print(f"Linking email '{email}' to Telegram chat ID '{chat_id}'...")
    
    # 1. Find user by email
    res = sb.table("users").select("id").eq("email", email).execute()
    if not res.data:
        print(f"Error: No user found with email '{email}'")
        return
    
    user_id = res.data[0]["id"]
    print(f"Found user ID: {user_id}")
    
    # 2. Update their telegram_chat_id
    try:
        update_res = sb.table("users").update({
            "telegram_chat_id": str(chat_id)
        }).eq("id", user_id).execute()
        
        print(f"Successfully linked {email} to Telegram!")
    except Exception as e:
        print(f"Error during update: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Link a Telegram chat ID to an existing email account.")
    parser.add_argument("email", help="The email of the existing account (e.g., Google account)")
    parser.add_argument("chat_id", help="The Telegram chat ID to link")
    
    args = parser.parse_args()
    link_account(args.email, args.chat_id)
