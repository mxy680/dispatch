"""
One-off helper script to create conversation tables in Supabase using environment variables.

Reads:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY

Usage (from repo root):
  cd server
  python scripts/init_supabase_conversation_tables.py
"""

import os
import sys

import httpx


DDL_SQL = """
create table if not exists public.conversation_turns (
  id text primary key,
  user_id text not null references public.users(id),
  project_id text references public.projects(id),
  session_id text references public.terminal_sessions(id),
  command_id text references public.terminal_commands(id),
  role text not null,
  turn_type text not null,
  content text not null,
  created_at timestamptz default now()
);

create table if not exists public.conversation_state (
  id text primary key,
  user_id text not null references public.users(id),
  project_id text references public.projects(id),
  active_command_id text references public.terminal_commands(id),
  state text not null default 'idle',
  context_json jsonb,
  updated_at timestamptz default now(),
  created_at timestamptz default now()
);
"""


def main() -> int:
  supabase_url = os.environ.get("SUPABASE_URL")
  service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

  if not supabase_url or not service_key:
    print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in the environment.", file=sys.stderr)
    return 1

  sql_endpoint = supabase_url.rstrip("/") + "/sql/v1"

  payload = {
    "query": DDL_SQL,
  }
  headers = {
    "apikey": service_key,
    "Authorization": f"Bearer {service_key}",
    "Content-Type": "application/json",
  }

  print(f"Creating conversation tables via {sql_endpoint} ...")
  with httpx.Client(timeout=30.0) as client:
    resp = client.post(sql_endpoint, json=payload, headers=headers)
  if resp.status_code >= 400:
    print(f"Supabase SQL error {resp.status_code}: {resp.text}", file=sys.stderr)
    return 1

  print("✅ conversation_turns and conversation_state created (or already existed).")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

