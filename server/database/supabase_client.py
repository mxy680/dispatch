# server/database/supabase_client.py
"""Supabase client singleton for database operations."""
import os
from typing import Optional
from supabase import create_client, Client

SUPABASE_URL = (
    os.environ.get("SUPABASE_URL")
    or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    or ""
)
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL:
    print("[DB] WARNING: SUPABASE_URL not set. Database operations will fail.")
if not SUPABASE_SERVICE_ROLE_KEY:
    print("[DB] WARNING: SUPABASE_SERVICE_ROLE_KEY not set. Database operations will fail.")

_client: Optional[Client] = None


def get_sb() -> Client:
    """Return a cached Supabase client using the service role key."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"
            )
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _client
