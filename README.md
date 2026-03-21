# CallStack

Voice and typed command orchestration for local coding agents.

## What is this?

CallStack lets developers speak or type coding requests in a hosted dashboard, then execute them on their own machine through a companion process. The companion bridges to local coding-agent CLIs (Cursor, Claude) and streams output back to the web app.

## Features

**Unified Command Center** — Voice and typed input feed one command timeline.

**Local Agent Bridge** — Commands execute locally on the user machine through the helper daemon.

**Provider-CLI First** — Supports Cursor CLI and Claude CLI (with shell fallback).

**Project Context Persistence** — Commands are grouped by project/session with durable history.

**Authentication** — Browser API uses Supabase JWT; local helper uses scoped agent tokens.

**Streaming Logs** — `stdout` / `stderr` logs stream back to the dashboard.

## How It Works

1. User speaks or types a request in Dashboard.
2. Backend parses intent and builds a provider CLI command.
3. Command is enqueued in `terminal_commands` (single execution queue).
4. Local helper claims the command, executes it in project context, and streams logs.
5. Dashboard timeline updates with status and output.

## Tech Stack

**Backend**: Python, FastAPI

**Speech**: Whisper (voice input path)

**Frontend**: React, Next.js

**Database**: SQLite

**Infrastructure**: Docker

## Getting Started

```bash
# Clone the repository
git clone https://github.com/mxy680/dispatch.git
cd dispatch

# Set up environment variables
cp .env.example .env
# Add your API keys for Twilio, Anthropic, Deepgram, ElevenLabs

# Install dependencies
pip install -r requirements.txt
npm install --prefix frontend

# Run the backend
uvicorn main:app --reload

# Pair and run local helper (from repo root)
python3 local-agent/dispatch_local_agent.py \
  --backend-url "http://localhost:8000" \
  --project-path "/absolute/path/to/project" \
  --agent-token "<token_from_dashboard_settings>"

# Launch the dashboard (separate terminal)
npm run dev --prefix web
```

## Companion and Cursor extension (scaffold)

- Desktop companion scaffold: `companion/`
- Cursor extension scaffold: `cursor-extension/`
- Architecture note: `docs/plans/2026-03-16-companion-cursor-scaffold.md`

*Full setup documentation coming soon.*

## Team

- Paulo Aguiar
- Zeynep Baştaş
- Mark Shteyn
- Ali Nawaf

---

Built for CSDS 393 Software Engineering at Case Western Reserve University
