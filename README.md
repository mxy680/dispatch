# Dispatch

Voice-controlled Claude Code orchestration via phone call.

## What is this?

Dispatch lets developers manage Claude Code instances on their local machine by calling a phone number. You talk to an AI orchestrator, issue coding commands, and your local Claude Code instance executes them—no keyboard required. A web dashboard handles project management and task history.

## Features

**Voice-to-Intent Parsing** — Natural language understanding that converts spoken commands into actionable coding tasks.

**Orchestrator Agent** — An AI intermediary that interprets your requests, manages context, and coordinates with your local machine.

**Claude Code Instance Management** — Spin up, monitor, and control Claude Code sessions remotely through voice commands.

**Twilio Telephony Integration** — Call from any phone, anywhere. The system handles the connection between your voice and your codebase.

**Project Context Persistence** — The orchestrator remembers your projects, preferences, and ongoing tasks across sessions.

**Authentication** — Secure access control so only you can command your development environment.

**Real-time Status Updates** — Get spoken feedback on task progress, errors, and completions during your call.

**Web Dashboard** — React-based interface for project management, viewing task history, and configuration.

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐     ┌─────────────┐     ┌─────────────┐
│             │     │             │     │                  │     │             │     │             │
│  Phone Call │────▶│   Twilio    │────▶│   Orchestrator   │────▶│ Local Agent │────▶│ Claude Code │
│             │     │             │     │                  │     │             │     │             │
└─────────────┘     └─────────────┘     └──────────────────┘     └─────────────┘     └─────────────┘
                                                │                                            │
                          STT (Deepgram/Whisper)│                                            │
                          TTS (ElevenLabs)      │                                            ▼
                                                │                                     ┌─────────────┐
                                                │                                     │             │
                                                └────────────────────────────────────▶│  Codebase   │
                                                         context & status             │             │
                                                                                      └─────────────┘
```

1. You call the Dispatch phone number
2. Twilio receives the call and streams audio to our orchestrator
3. Speech-to-text converts your voice to commands
4. The orchestrator interprets intent and sends instructions to your local agent
5. The local agent manages Claude Code execution on your machine
6. Results flow back through the chain as spoken responses

## Tech Stack

**Backend**: Python, FastAPI, Anthropic SDK

**Telephony**: Twilio Voice API

**Speech**: Deepgram or Whisper (STT), ElevenLabs (TTS)

**Frontend**: React, Next.js

**Database**: SQLite (dev), PostgreSQL (prod)

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

# Run the local agent
python agent/main.py

# Start the orchestrator server
python server/main.py

# Launch the dashboard (separate terminal)
npm run dev --prefix frontend
```

*Full setup documentation coming soon.*

## Team

- Paulo Aguiar
- Zeynep Baştaş
- Mark Shteyn
- Ali Nawaf

---

Built for CSDS 393 Software Engineering at Case Western Reserve University
