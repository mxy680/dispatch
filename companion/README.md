# Dispatch Companion

Cross-platform desktop companion for macOS/Windows/Linux. Receives commands from the Dispatch backend, executes them locally via Cursor or Claude CLI, and streams output back.

## Quick start

```bash
cd companion
npm install
```

### 1) Pair with your account

In the web app: Settings -> Create pairing code.

Then:

```bash
node src/index.js pair http://localhost:8000 <pairing-code>
```

### 2) Set up projects and Cursor

```bash
node src/index.js setup
```

This interactive wizard will:
- Detect if Cursor CLI is installed
- Show currently linked projects
- Let you link a local project folder
- Optionally open Cursor in that folder

### 3) Run the companion

```bash
npm start
```

This starts:
- **Command worker**: heartbeats, claims queued commands, executes locally, streams logs.
- **Localhost bridge** on `http://127.0.0.1:43111`: accepts Cursor extension context.

### 4) Send commands

In the Dashboard Unified Command Center:
- Pick a project and provider (Cursor / Claude / Shell).
- Type or speak a command.
- Watch output appear in the timeline.

Tip: if you want to run literal shell commands like `ls`, `pwd`, or `git status`, use the **Manual Bash Terminal** section (provider `shell`). Cursor provider is best for coding prompts, not raw shell utilities.

## Supported providers

- **Cursor** (default): `agent -p "<prompt>" --output-format text`
- **Claude**: `claude -p "<prompt>"`
- **Shell**: raw command executed as-is

## Cursor extension bridge

The companion exposes `POST http://127.0.0.1:43111/context` for the Cursor extension to push editor context (active file, selection, diagnostics).

## Troubleshooting

- If you see `/bin/sh: agent: command not found`, run:
  - `node src/index.js setup`
  - This re-detects and stores the absolute `agent` binary path for the worker.
