# Testing Documentation

## Overview

The backend test suite contains **474 tests** across 21 test files, covering the FastAPI server, database layer, service modules, and agent pipeline. Overall code coverage is **88%**.

Frontend component tests are written in Vitest and located in the `web/` package.

---

## Where Tests Are Located

```
server/tests/
├── conftest.py                   # Shared fixtures — in-memory Supabase mock
├── test_security_analyzer.py     # AI risk classification (99% coverage)
├── test_dispatcher.py            # Agent dispatch pipeline
├── test_command_builder.py       # CLI command construction (100% coverage)
├── test_main_routes.py           # Settings, dashboard, tasks, agent endpoints
├── test_main_extra.py            # Phone, project, dispatch, helper routes
├── test_main_extra2.py           # Device, agent-token, terminal, unified-reply
├── test_models.py                # Supabase database model functions
├── test_models_supabase.py       # Additional model layer tests
├── test_sidecar_store.py         # SQLite sidecar CRUD (97% coverage)
├── test_agents_and_llm.py        # copilot_agent, prompt_refiner, LLM service
├── test_services.py              # Telegram and transcription services (100% coverage)
├── test_property_based.py        # Hypothesis property-based tests
├── test_phone_verification.py    # Twilio Verify OTP flow
├── test_telegram.py              # Telegram bot handler
├── test_dispatch.py              # End-to-end dispatch pipeline
├── test_api.py                   # API endpoint smoke tests
├── test_api_endpoints.py         # Additional API endpoint tests
├── test_call_sessions.py         # Twilio call session lifecycle
├── test_companion_models.py      # Companion device models
└── test_unified_pipeline_models.py  # Unified command pipeline models

web/
├── components/unified-command-center.test.tsx   # Command center component
└── lib/supabase/access-token.test.ts            # Token utility tests
```

---

## What Is Covered

### Backend (pytest)

| Module | Coverage | Tests |
|---|---|---|
| `agents/command_builder.py` | 100% | Provider normalization, CLI command construction for cursor/claude/shell |
| `agents/copilot_agent.py` | 100% | Copilot agent prompt building and response parsing |
| `agents/prompt_refiner.py` | 100% | Prompt refinement pipeline |
| `services/security_analyzer.py` | 99% | SAFE/WARNING/HIGH_RISK heuristics, LLM path, fallback, `_normalize_level` |
| `services/telegram.py` | 100% | Webhook handling, intent dispatch, reply formatting |
| `services/transcription.py` | 100% | Whisper API call, timeout/connection/status error handling |
| `services/phone_verification.py` | 95% | Twilio Verify send and check OTP |
| `database/sidecar_store.py` | 97% | SQLite conversation turns, dialogue state, command risk records |
| `agents/dispatcher.py` | 93% | Task resolution, provider command queuing, execution tracking |
| `main.py` | 79% | Settings, dashboard, project, task, device, agent-token, terminal, unified, Telegram, Twilio routes |
| `database/models.py` | 72% | Supabase PostgREST operations for users, projects, tasks, executions |

**Overall: 88% across 474 tests**

### Test strategies applied

**1. Mock-object testing** — All external dependencies (Supabase, Groq LLM, Twilio, file system) are replaced with `unittest.mock` patches. The shared `conftest.py` provides a chainable in-memory Supabase mock so the suite runs without real credentials or network access.

**2. Property-based testing (Hypothesis)** — `test_property_based.py` verifies invariants that hold for any input:
- `_normalize_level(s)` always returns one of `{SAFE, WARNING, HIGH_RISK}`
- `normalize_provider(s)` always returns one of `{cursor, claude, shell}`
- `build_provider_command(provider, prompt)` always contains the prompt and required flags

**3. Mutation testing (mutmut)** — Applied to `services/security_analyzer.py` and `agents/command_builder.py`. Initial run found 70 surviving mutants in the security analyzer. Targeted tests reduced this to 49 (30% improvement). The mutation config is in `server/mutmut_config.py`.

**4. CI/CD regression testing** — GitHub Actions (`.github/workflows/test.yml`) runs the full suite on every push to every branch. Coverage is uploaded as an artifact on each run.

### Frontend (Vitest)

Frontend tests cover the `unified-command-center` component and the Supabase access-token utility. Coverage is partial — the backend test suite is the primary quality gate.

---

## How to Run

### Prerequisites

```bash
cd server
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt pytest pytest-asyncio pytest-cov hypothesis eval_type_backport
```

No real API keys are needed. Set these environment variables (or let the defaults apply — `conftest.py` patches the Supabase client):

```bash
export SUPABASE_URL=https://placeholder.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=placeholder-key
export GROQ_API_KEY=placeholder-key
export DEVELOPMENT_MODE=true
```

### Run all tests

```bash
cd server
python -m pytest -q
```

### Run with coverage report

```bash
python -m pytest --cov=. --cov-report=term-missing
```

### Run a single test file

```bash
python -m pytest tests/test_security_analyzer.py -v
```

### Run mutation testing

```bash
cd server
mutmut run
mutmut results
```

### Run frontend tests

```bash
cd web
npm install
npm run test:run
```

---

## Advanced Quality Artifacts (CSDS 493)

### Coverage report

A full coverage report is stored at [`demo 4/coverage_report.txt`](demo%204/coverage_report.txt). HTML coverage output can be generated locally:

```bash
cd server
python -m pytest --cov=. --cov-report=html
open coverage_html/index.html
```

### Mutation testing report

Mutation testing results are documented in [`demo 4/mutation_report.txt`](demo%204/mutation_report.txt). The mutmut configuration is at [`server/mutmut_config.py`](server/mutmut_config.py).

**Result:** 70 surviving mutants in `security_analyzer.py` reduced to 49 (30% killed) after targeted test additions. This uncovered 21 edge cases that line coverage alone would not have caught.

### CI pipeline

The GitHub Actions pipeline (`.github/workflows/test.yml`) runs automatically on every push:
- Python 3.9, pip-cached dependencies
- Full pytest suite with `--cov` and `--tb=short`
- Coverage artifact uploaded for 7 days per run
- Placeholder credentials allow the suite to run without secrets

---

## Important Limitations

- **No real external calls in tests** — Supabase, Groq, and Twilio are always mocked. Passing tests do not guarantee the live integrations work; those require a real `.env` with valid credentials.
- **`main.py` coverage is 79%** — Routes that depend on complex Twilio call-flow state or multi-step device pairing are partially covered by mocks but not fully exercised end-to-end.
- **Frontend coverage is low** — Only two frontend test files exist. UI correctness beyond those components is validated manually.
- **Mutation testing scope** — mutmut was applied only to `security_analyzer.py` and `command_builder.py`. Other modules were not mutation-tested.
- **Python 3.9 target** — The suite runs on Python 3.9 to match the CI environment. `eval_type_backport` is required for Pydantic V2 compatibility on 3.9.
