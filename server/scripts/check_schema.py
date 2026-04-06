import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.supabase_client import get_sb

def check():
    sb = get_sb()
    try:
        res = sb.table("users").select("*").limit(1).execute()
        if res.data:
            print(f"Columns: {list(res.data[0].keys())}")
        else:
            print("No users found in table.")
            # Try to get columns anyway by selecting a non-existent row
            res = sb.table("users").select("*").eq("id", "none").execute()
            # If still no data, we might not get keys easily from PostgREST without data
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check()
