# Dispatch

[![Tests](https://github.com/mxy680/dispatch/actions/workflows/test.yml/badge.svg)](https://github.com/mxy680/dispatch/actions/workflows/test.yml)

**Live app:** https://web-zeynepbastas-zeynepbastas-projects.vercel.app  
**API:** https://dispatch-api.fly.dev

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

### Command lifecycle sequence

```
User            FastAPI Backend       Security Analyzer    Local Agent Daemon    Claude/Cursor CLI
 │                    │                      │                     │                    │
 │──voice/text──────▶│                      │                     │                    │
 │                    │──parse intent───────▶│                     │                    │
 │                    │   (Groq LLM)         │                     │                    │
 │                    │◀─ intent JSON ───────│                     │                    │
 │                    │                      │                     │                    │
 │                    │──analyze command────▶│                     │                    │
 │                    │                      │─ classify ─────────▶│                    │
 │                    │◀─ SAFE/WARNING/──────│                     │                    │
 │                    │   HIGH_RISK          │                     │                    │
 │                    │                      │                     │                    │
 │                    │── save command ──────────────────────────▶│                    │
 │                    │   (pending_approval) │                     │                    │
 │◀── dashboard ──────│                      │                     │                    │
 │    shows command   │                      │                     │                    │
 │                    │                      │                     │                    │
 │──approve──────────▶│                      │                     │                    │
 │  (voice/click)     │── set approved ──────────────────────────▶│                    │
 │                    │                      │                     │                    │
 │                    │                      │                     │──claim command─────▶│
 │                    │                      │                     │──execute───────────▶│
 │                    │                      │                     │◀─ stream logs ──────│
 │◀── live logs ──────│◀─────────────────────────────────────────│                    │
```

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

## Usage Example

Once the backend, frontend, and local agent are all running:

**1. Connect your local agent**

```bash
python local-agent/dispatch_local_agent.py \
  --backend-url http://localhost:8000 \
  --project-path /path/to/your/project \
  --agent-token <token-from-settings>
```

**2. Issue a command**

Open the dashboard at `http://localhost:3000`. In the Unified Command Center, type:

```
refactor the auth module to use async/await
```

Or call your Twilio number and speak it, or send it via Telegram.

**3. Review the security classification**

The AI Security Analyzer classifies the command. For the example above you'd see:

```
Risk: SAFE
Reason: Code refactoring operation with no destructive or network side effects.
```

A command like `rm -rf /tmp/build` would show `HIGH_RISK` and require explicit UI confirmation — voice approval is blocked for high-risk commands.

**4. Approve and watch it run**

Click **Approve** in the dashboard (or say "yes" / "approve" if you're on a voice call). The local agent claims the command, runs `claude -p "refactor the auth module to use async/await"` in your project directory, and streams the output back line by line into the dashboard log viewer.

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
python -m pytest -q                          # run all 474 tests
python -m pytest --cov=. --cov-report=term-missing  # with coverage report
```

### Test strategy — four methods applied

**1. Mock-object testing** is used throughout so the suite runs without real Supabase credentials, API keys, or network access. A shared `conftest.py` provides a chainable in-memory Supabase mock. Additional patches use `unittest.mock` to isolate every external dependency.

**2. Property-based testing** (Hypothesis) verifies invariants that hold for any input, not just hand-picked examples:
- `_normalize_level(s)` always returns one of `{SAFE, WARNING, HIGH_RISK}`
- `normalize_provider(s)` always returns one of `{cursor, claude, shell}`
- `build_provider_command(provider, prompt)` always contains the prompt and required flags

**3. Mutation testing** with `mutmut` was applied to `agents/command_builder.py` and `services/security_analyzer.py`. Initial run found 70 surviving mutants in the security analyzer. Targeted tests reduced this to 49 (30% improvement). See `demo 4/mutation_report.txt`.

```bash
cd server && mutmut run && mutmut results
```

**4. CI/CD regression testing** — GitHub Actions runs the full suite on every push. Every failing commit is caught before it reaches `main`.

Key test files:

| File | What it covers |
|---|---|
| `test_security_analyzer.py` | All HIGH_RISK/WARNING/SAFE patterns, LLM path, fallback, helpers |
| `test_dispatcher.py` | Agent dispatch pipeline, task resolution, terminal command creation |
| `test_command_builder.py` | Provider normalization, CLI command construction |
| `test_main_routes.py` | Settings, dashboard, tasks, agent, unified endpoints |
| `test_main_extra.py` | Helper functions, phone, project, dispatch routes |
| `test_main_extra2.py` | Device, agent-token, terminal, unified-reply, transcribe-text |
| `test_property_based.py` | Hypothesis property tests across three modules |
| `test_sidecar_store.py` | SQLite sidecar — conversation turns, state, command risk |
| `test_agents_and_llm.py` | copilot_agent, prompt_refiner, LLM service, Supabase client |
| `test_services.py` | Telegram and transcription services |
| `test_models.py` | Supabase model functions (51 tests) |

### Coverage

Overall: **88%** across 474 tests — see `demo 4/coverage_report.txt` for the full breakdown.

Highlight modules:
- `agents/command_builder.py` — 100%
- `agents/copilot_agent.py` — 100%
- `agents/prompt_refiner.py` — 100%
- `agents/dispatcher.py` — 93%
- `services/security_analyzer.py` — 99%
- `services/telegram.py` — 100%
- `services/transcription.py` — 100%
- `services/llm.py` — 97%
- `services/phone_verification.py` — 95%
- `database/sidecar_store.py` — 97%
- `main.py` — 79%

## AI-Assisted Development

[Claude Code](https://claude.ai/code) and [Cursor](https://cursor.sh) were used throughout development.

- **Cursor** was used for scaffolding Next.js components (the Risk Shield UI, Unified Command Center), backend refactoring, and writing Supabase migration DDL. Cursor's `@workspace` context allowed generated components to match existing Tailwind configuration automatically.
- **Claude Code** was used for test infrastructure work: diagnosing and fixing Python 3.9 compatibility issues across the codebase, building the conftest mock fixture, running and interpreting mutation testing results, and expanding the security analyzer test suite from 2 tests to 37 based on mutation findings.

All AI-generated code was reviewed and tested before merging.

## API Documentation

Auto-generated HTML documentation for all backend modules is in [`api-docs/`](api-docs/index.html). Open `api-docs/index.html` in a browser after cloning. Generated with [pdoc](https://pdoc.dev).

To regenerate:

```bash
cd server
pip install pdoc
PYTHONPATH=. pdoc agents.command_builder agents.dispatcher agents.copilot_agent \
  agents.prompt_refiner services.security_analyzer services.llm services.transcription \
  services.phone_verification database.models database.sidecar_store main \
  --output-dir ../api-docs
```

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

| Member | Role | Key Contributions |
|---|---|---|
| Mark Shteyn | Full-stack Lead | Project initialization; Next.js frontend (dashboard, bento grid, shadcn/ui); FastAPI server bootstrap; SQLite → Supabase Postgres migration; Groq integration; Twilio SMS OTP; real-time log streaming; agent command claiming and stale-command recovery |
| Zeynep Baştaş | Testing, Backend & Project Coordination | Full pytest test suite (474 tests, 88% coverage); CI/CD GitHub Actions pipeline; mutation testing with mutmut; property-based testing with Hypothesis; rate limiting via slowapi; Twilio voice webhooks, call history API and call history page (frontend); end-to-end Twilio voice pipeline debugging and verification; database API endpoints for projects and tasks; real-time dashboard polling; initial SQLite database setup and CRUD; transcription error handling; Python 3.9 compatibility; project-wide documentation (README, testing.md, docstrings, pdoc API docs); Trello board setup and sprint tracking; TA communication and in-team coordination |
| Paulo Aguiar | Integrations | Telegram bot (bulk implementation and webhook handler); local agent daemon; initial project structure and database schema for intent parsing and call logs |
| Ali Nawaf | Security & Agent Features | AI security analyzer; approval gate for sensitive voice commands; terminal agent connections with tokens; centralized agent orchestration; coding agent support (Claude/Cursor); access token cache, settings, and danger zone UI; Electron companion app scaffold; file watcher; intent parsing; voice agent transcription integration |

## Retrospective

### What went well

- **AI-assisted development** — Cursor handled frontend scaffolding and Claude Code handled test infrastructure, which cut boilerplate time significantly. Both tools were used with code review before merging.
- **Security-first design** — The approval gate and AI security analyzer were built early, so every subsequent feature inherited those guarantees without retrofit work.
- **Mutation testing payoff** — Running mutmut revealed 70 surviving mutants in the security analyzer that normal coverage metrics didn't surface. Closing 30% of those with targeted tests gave much higher confidence in the most critical module.
- **Mock-based CI from day one** — The shared `conftest.py` Supabase mock let every contributor write and run tests without real credentials, and the GitHub Actions pipeline worked from the first commit.

### What we would do differently

- **Finalize the database schema earlier** — Mid-project schema changes required coordinating migrations across branches and occasionally blocked parallel work. A stable schema agreed on at week 2 would have removed integration friction.
- **Add types to the backend up front** — Adding Pydantic return types and annotations to `models.py` retroactively was slower than writing them first. Full typing at initial implementation would have caught bugs at development time instead of test time.
- **Invest in frontend tests in parallel with features** — Backend coverage is 88%; frontend Vitest coverage is lower. Writing component tests alongside features would have improved UI confidence throughout the project.

## License

MIT License — see [LICENSE](LICENSE) for details.

---

Built for CSDS 393/493 Software Engineering at Case Western Reserve University.
