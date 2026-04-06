# Demo 4 - Testing and QA Pack



## Where the tests are

Backend tests are in:

- `server/tests/test_security_analyzer.py`
- `server/tests/test_api_endpoints.py`
- `server/tests/test_models.py`
- `server/tests/test_companion_models.py`
- `server/tests/test_unified_pipeline_models.py`
- plus other supporting tests in `server/tests/`

Core config:

- `server/pytest.ini`
- `server/tests/conftest.py`

## Feature-to-test mapping (mock-object strategy)

### 1) AI Security Analyzer

- Main implementation:
  - `server/services/security_analyzer.py`
  - called from `server/main.py` in `_background_security_scan(...)`
- Existing tests:
  - `server/tests/test_security_analyzer.py` (heuristic path)
- Mock-object target:
  - mock the LLM call (OpenAI/Groq client) and return structured JSON
  - assert parsing and downstream risk persistence behavior

### 2) Voice Approval Intent Router

- Main implementation:
  - `server/main.py`
  - `_is_affirmation_intent(...)`, `_classify_reply(...)`, and `/api/unified/reply`
- Existing tests:
  - `server/tests/test_api_endpoints.py` (approval and risk-gated reply flows)
- Mock-object target:
  - mock model/database functions and assert status transition attempts from `pending_approval` -> `queued` on approve intent

## How to run tests

From repo root:

```bash
cd server
python -m pytest -q
```

Targeted runs:

```bash
# Security analyzer tests
python -m pytest tests/test_security_analyzer.py -q

# API endpoint approval/voice flows
python -m pytest tests/test_api_endpoints.py -q

# Models and sidecar behavior
python -m pytest tests/test_models.py -q
```

## Coverage and mutation testing

If needed, install helpers:

```bash
cd server
python -m pip install pytest-cov mutmut
```

Coverage:

```bash
python -m pytest --cov=. --cov-report=term-missing
```

Mutation testing (example):

```bash
mutmut run --paths-to-mutate services/security_analyzer.py
mutmut results
```

## What was done for this demo

1. Confirmed and documented where all test suites live.
2. Mapped two required advanced mock-object features to concrete backend files and existing tests.
3. Provided copy-paste commands for full test runs, targeted runs, coverage, and mutation checks.
4. Kept all newly generated artifacts in this `demo 4` folder.
