# CallStack Local Agent (Terminal Bridge)

This folder contains a **local helper daemon** that runs on a user's machine and connects to the hosted CallStack backend to execute terminal commands locally and stream output back.

## What it does

- Registers a local instance for a `project_id`
- Sends heartbeats
- Pulls queued terminal commands for its instance
- Executes commands locally
- Streams `stdout`/`stderr` as chunked logs
- Marks commands as `completed`/`failed`

## Requirements

- Python 3.10+
- A Supabase access token (JWT) from the CallStack web app session (for now)

## Run

```bash
python3 local-agent/dispatch_local_agent.py \
  --backend-url "http://localhost:8000" \
  --project-id "<your-project-id>" \
  --project-path "/absolute/path/to/your/project" \
  --auth-token "<supabase_access_token>"
```

In development, if the backend runs with `DEVELOPMENT_MODE=true`, you can omit `--auth-token` and it will fall back to the backend mock user.

## Security notes

- This agent runs **as your local OS user** and can execute commands with your permissions.\n+- Only run it on machines you trust.\n+- For public SaaS hardening, replace `--auth-token` with a dedicated device token / API key flow.

