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

## Pair and run (recommended)

1) In the web app, go to **Dashboard → Settings → Agents** and click **Create agent token**.\n2) Copy the token and run:

```bash
python3 local-agent/dispatch_local_agent.py \
  --backend-url "http://localhost:8000" \
  --project-path "/absolute/path/to/your/project" \
  --agent-token "<agent_token_from_settings>"
```

Optional:

- `--project-name "MyProject"` (otherwise the folder name is used)
- `--project-id "<project_id>"` (if you want to bind to an existing project)

In development, if the backend runs with `DEVELOPMENT_MODE=true`, the web UI calls may still work without auth, but agent pairing always uses `--agent-token`.

## Provider CLIs

The unified pipeline sends commands to your chosen local provider:

- `cursor` -> `cursor --command "<prompt>"`
- `claude` -> `claude -p "<prompt>"`
- `shell` -> raw shell command

Install Cursor CLI or Claude CLI locally for best results.

## Security notes

- This agent runs **as your local OS user** and executes commands with your permissions.
- Only run it on machines you trust.
- For public SaaS hardening, replace broad command execution with allowlists and policy checks.

