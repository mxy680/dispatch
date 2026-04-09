# Dispatch

[![Tests](https://github.com/mxy680/dispatch/actions/workflows/test.yml/badge.svg)](https://github.com/mxy680/dispatch/actions/workflows/test.yml)

Voice and typed command orchestration for local coding agents.

## What is this?

Dispatch lets developers control coding agents on their local machine by speaking or typing commands in a hosted dashboard. You issue a request — via voice call, Telegram, or the web UI — and your local machine executes it through a connected companion process. An AI security layer reviews every command before it runs, and you approve or reject it hands-free by speaking.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Voice Call  │────▶│    Twilio    │────▶│                  │
│  (phone)     │     │              │     │   FastAPI        │
└──────────────┘     └──────────────┘     │   Backend        │
                                          │                  │
┌──────────────┐                          │  - Intent parse  │
│  Telegram    │─────────────────────────▶│  - Security scan │
│  Bot         │                          │  - Approval gate │
└──────────────┘                          │                  │
                                          └────────┬─────────┘
┌──────────────┐                                   │
│  Web UI      │◀──────── dashboard / logs ────────┤
│  (Next.js)   │                                   │
└──────────────┘                          ┌────────▼─────────┐
                                          │  Local Agent     │
                                          │  Daemon          │
                                          │  (companion)     │
                                          └────────┬─────────┘
                                                   │
                                          ┌────────▼─────────┐
                                          │  Claude / Cursor  │
                                          │  CLI              │
                                          └──────────────────┘
```

### How a command flows

1. User speaks, types in the dashboard, or sends a Telegram message.
2. Backend parses the intent (via Groq LLM) and builds a CLI command.
3. AI Security Analyzer classifies the command as `SAFE`, `WARNING`, or `HIGH_RISK`.
4. Command is placed in `pending_approval` state — the local agent will not run it yet.
5. User approves (by speaking "yes", "approve", etc. or clicking in the UI).
6. Local agent daemon claims the command, executes it in the project directory, and streams logs back.
7. Dashboard updates in real time with status and output.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Uvicorn |
| Database | Supabase (Postgres) |
| Frontend | Next.js 16, React 19, Tailwind CSS, shadcn/ui |
| Speech-to-text | Groq Whisper API |
| LLM (intent + security) | Groq (llama-3.3-70b-versatile) |
| Voice calls | Twilio |
| SMS verification | Twilio Verify |
| Local agent | Python daemon (`local-agent/dispatch_local_agent.py`) |

## Getting Started

### Prerequisites

- Python 3.9+
- Node.js 18+
- A [Supabase](https://supabase.com) project
- A [Groq](https://console.groq.com) API key
- (Optional) Twilio account for voice calls and SMS

### 1. Clone and configure environment

```bash
git clone https://github.com/mxy680/dispatch.git
cd dispatch
cp .env.example .env
```

Fill in `.env`:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
GROQ_API_KEY=your-groq-key

# Optional — for voice calls and SMS OTP
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
TWILIO_VERIFY_SERVICE_SID=

# Optional — for Telegram bot
TELEGRAM_BOT_TOKEN=
TELEGRAM_SECRET_TOKEN=
```

Fill in `web/.env.local` (copy from `web/.env.local.example`):

```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

### 2. Run the backend

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Run the frontend

```bash
cd web
npm install
npm run dev
```

The dashboard is available at `http://localhost:3000`.

### 4. Connect the local agent

The local agent daemon bridges the backend to your machine. Run it in the project directory you want to control:

```bash
python local-agent/dispatch_local_agent.py \
  --backend-url http://localhost:8000 \
  --project-path /absolute/path/to/your/project \
  --agent-token <token-from-dashboard-settings>
```

The agent token is generated in the dashboard under Settings → Agents.

## Features

**Unified Command Center** — Voice and typed input feed a single command timeline with real-time log streaming.

**AI Security Analyzer** — Every command is classified `SAFE`, `WARNING`, or `HIGH_RISK` by an LLM before execution. High-risk commands cannot be voice-approved and require explicit confirmation.

**Approval Gate** — Commands default to `pending_approval`. The local agent never executes a command without explicit user approval, preventing accidental destructive operations.

**Voice Approval** — Speak "yes", "approve", "run it", etc. to approve a pending command, or "no", "cancel" to reject. The intent router handles natural affirmations.

**Telegram Bot** — Send commands via Telegram. The bot parses intent, dispatches to the local agent, and replies with status.

**Phone Calls** — Call a Twilio number, speak your request, and the system transcribes and dispatches it.

**Project Management** — Commands are grouped by project with persistent task history.

**Provider Support** — Supports Claude Code CLI and Cursor CLI, with shell fallback for raw commands.

## Testing

```bash
cd server
python -m pytest -q                          # run all 229 tests
python -m pytest --cov=. --cov-report=term-missing  # with coverage report
```

### Test strategy

Mock-object testing is used throughout so the suite runs without real Supabase credentials or API keys. A shared `conftest.py` fixture provides a chainable Supabase mock that correctly handles both list queries (`data = []`) and single-row queries (`maybe_single().execute().data = None`).

Key test files:

| File | What it tests |
|---|---|
| `test_security_analyzer.py` | Heuristic fallback — all HIGH_RISK/WARNING/SAFE patterns, response structure, helper functions |
| `test_dispatcher.py` | Agent dispatch pipeline — task resolution, terminal command creation, access gating |
| `test_command_builder.py` | Provider normalization and CLI command construction |
| `test_api_endpoints.py` | REST API — projects, unified commands, phone verification, approval flows |
| `test_api.py` | Telegram webhook, dashboard, health endpoints |
| `test_models.py` | Supabase model functions |

### Mutation testing

Mutation testing was applied to `agents/command_builder.py` and `services/security_analyzer.py` using `mutmut`:

```bash
cd server
pip install mutmut
mutmut run
mutmut results
```

This identified 70 surviving mutants in the heuristic security analyzer (gaps in pattern coverage). After adding targeted tests, the score improved to 49 survived — a 30% reduction. Results are documented in `demo 4/mutation_report.txt`.

### Coverage

Overall: **74%** — see `demo 4/coverage_report.txt` for the full breakdown.

Highlight modules:
- `agents/command_builder.py` — 100%
- `agents/dispatcher.py` — 93%
- `services/phone_verification.py` — 95%
- `database/models.py` — 67%

## AI-Assisted Development

[Claude Code](https://claude.ai/code) and [Cursor](https://cursor.sh) were used throughout development.

- **Cursor** was used for scaffolding Next.js components (the Risk Shield UI, Unified Command Center), backend refactoring, and writing Supabase migration DDL. Cursor's `@workspace` context allowed generated components to match existing Tailwind configuration automatically.
- **Claude Code** was used for test infrastructure work: diagnosing and fixing Python 3.9 compatibility issues across the codebase, building the conftest mock fixture, running and interpreting mutation testing results, and expanding the security analyzer test suite from 2 tests to 37 based on mutation findings.

All AI-generated code was reviewed and tested before merging.

## Project Structure

```
dispatch/
├── server/                  # FastAPI backend
│   ├── main.py              # API routes
│   ├── agents/              # Dispatcher, command builder
│   ├── services/            # LLM, security analyzer, Telegram, Twilio
│   ├── database/            # Supabase models and client
│   └── tests/               # Full test suite
├── web/                     # Next.js frontend
│   ├── app/                 # Pages and layout
│   ├── components/          # UI components
│   └── lib/voice/           # VAD loop, TTS, earcons
├── local-agent/             # Local agent daemon
│   └── dispatch_local_agent.py
├── companion/               # Electron desktop companion (scaffold)
├── cursor-extension/        # Cursor IDE extension (scaffold)
└── demo 4/                  # Demo artifacts: coverage and mutation reports
```

## Team

- Paulo Aguiar
- Zeynep Baştaş
- Mark Shteyn
- Ali Nawaf

---

Built for CSDS 393 Software Engineering at Case Western Reserve University.
