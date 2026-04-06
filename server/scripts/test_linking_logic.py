import os
import sys
import uuid
from dotenv import load_dotenv

# Path setup
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), 'server')))
load_dotenv(os.path.join(os.getcwd(), 'server', '.env'))

from database import models

def test():
    chat_id = "8223456138"
    email = "pfa14@case.edu"
    
    print(f"Testing linking {chat_id} to {email}...")
    try:
        models.set_local_telegram_link(chat_id, email)
        print("✅ set_local_telegram_link Success!")
        
        user_id = models.get_user_id_by_telegram_chat_id(chat_id)
        print(f"✅ get_user_id_by_telegram_chat_id: {user_id}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test()
