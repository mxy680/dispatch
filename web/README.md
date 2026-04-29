# Dispatch — Web Frontend

Next.js 16 dashboard for the Dispatch voice and command orchestration platform.

## What it does

- **Unified Command Center** — type or record voice commands that are dispatched to your local coding agent
- **Real-time log streaming** — watch Claude/Cursor output stream into the dashboard as it runs
- **AI security risk display** — every command shows its SAFE / WARNING / HIGH_RISK classification before execution
- **Approval gate** — approve or reject pending commands from the UI
- **Project and task management** — group commands by project with persistent history
- **Settings** — configure provider (Claude/Cursor/shell), base project path, agent tokens, phone OTP

## Tech stack

| Layer | Technology |
|---|---|
| Framework | Next.js 16, React 19 |
| Styling | Tailwind CSS v4, shadcn/ui, Radix UI |
| Auth | Supabase Auth (Google OAuth) |
| Database client | @supabase/supabase-js |
| Testing | Vitest |

## Setup

```bash
npm install
cp .env.local.example .env.local
```

Fill in `.env.local`:

```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

```bash
npm run dev        # development server at http://localhost:3000
npm run build      # production build
npm run test:run   # run Vitest tests
```

## Folder structure

```
web/
├── app/
│   ├── auth/          # Supabase OAuth callback
│   ├── dashboard/     # Main dashboard page
│   └── login/         # Login page
├── components/        # UI components (command center, log viewer, voice recorder, etc.)
├── lib/
│   ├── supabase/      # Supabase client utilities and token helpers
│   └── voice/         # VAD loop, TTS, earcons
└── test/              # Vitest setup
```

## Live deployment

https://web-zeynepbastas-zeynepbastas-projects.vercel.app
