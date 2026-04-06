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


# Dispatch: Demo 4 - Complete System & AI Security Pipeline

This document outlines the major architectural choices, code quality standards, and development workflows for the Demo 4 milestone of the **Dispatch** platform. Dispatch is a voice-controlled orchestration system designed for secure, local execution of CLI commands via a connected companion agent. 

For this demo, we successfully integrated the front-end, back-end, and database, while introducing a sophisticated **AI Security Analyzer** and **Voice Approval Gate** as our advanced features.

---

## 1. Major Workflow and Architectural Choices

To solve the "rogue agent" problem and eliminate the confusion of maintaining separate pipelines for voice and text commands, we transitioned to a **Unified Execution Substrate**.

* **The Unified Pipeline:** All commands—whether spoken via the browser VAD (Voice Activity Detection) or typed in the terminal UI—now resolve to a single `terminal_commands` database table. 
* **The Approval Gate (Default Deny):** By default, every command is placed in a `pending_approval` state. The local companion will *never* execute a command unless it explicitly transitions to a `queued` state.
* **AI Security Analyzer:** Before the user is prompted to approve a command, a FastAPI background task sends the command intent to a security-tuned LLM. The LLM acts as an asynchronous safety layer, categorizing the command's `risk_level` (SAFE, WARNING, HIGH_RISK) and providing a `risk_reason` (e.g., flagging `rm -rf`).
* **Hands-Free Resolution:** To maintain a seamless voice UX, the backend `IntentRouter` parses incoming speech for affirmation turns (e.g., "Yes," "Approve," "Execute"). This transitions the command status entirely hands-free, bridging the gap between security and convenience.

---

## 2. Code Quality and Software Standards

A major focus of Demo 4 was ensuring the codebase is scalable, maintainable, and resilient.

### Modularity and Architecture
* **Backend Separation of Concerns:** We enforced strict modularity in the Python backend. The `main.py` file acts purely as a routing layer. Complex business logic was extracted into dedicated service modules, such as `server/services/security_analyzer.py` (handling the LLM risk assessment) and `server/services/intent_router.py` (handling state transitions).
* **Frontend Component Isolation:** The Next.js web app is broken down into isolated client components. The `UnifiedCommandCenter` manages state, while sub-components handle the Voice/VAD loop and the dynamic Risk Shield UI independently.

### Software Quality: Error Handling & Resilience
* **Graceful Degradation:** External API calls (like the LLM security analysis) are wrapped in `try/except` blocks with designated timeouts. If the AI analyzer fails or the network drops, the system defaults to `PENDING` (manual review required) rather than crashing or auto-approving a potentially dangerous command.
* **State Management:** The frontend actively listens to state changes. If a command is rejected or errors out, the UI immediately updates without requiring a page refresh, preventing desync between the user's view and the database.

### Usability and Appearance
* **Aesthetic Design:** The UI was designed with a minimalist, high-contrast aesthetic. It utilizes a deep dark theme (`#1a1a1a` background, `#242424` cards) accented by Supabase Green (`#3ECF8E`). 
* **Visual State Cues (The Risk Shield):** Usability is enhanced through immediate visual feedback. The UI dynamically renders a "Security Shield" above pending commands—displaying a green checkmark for safe commands, an amber alert for warnings, and a red shield for high-risk destructive commands, ensuring the user is fully informed before approving.

---

## 3. AI-Assisted Development (Cursor Workflow)

To accelerate development and maintain high coding standards, **Cursor** was utilized extensively as the primary AI coding assistant throughout this sprint. 

* **Context-Aware Scaffolding:** Using Cursor's `@workspace` feature, we generated the Next.js Risk Shield components. Because Cursor understood the existing Tailwind configuration, the generated code perfectly matched our custom color palette and dark theme out of the box.
* **Backend Refactoring:** Cursor's inline chat was instrumental in refactoring the monolithic backend. It assisted in breaking out the conversational logic into the `IntentRouter` service and automatically generating the necessary Python type hints and docstrings to enforce our coding standards.
* **Database Migrations:** We leveraged Cursor to write the exact PostgreSQL DDL scripts required to update the Supabase schema, adding the `risk_level` and `risk_reason` columns to the `terminal_commands` table without syntax errors.

---

## 4. Verification and Correctness (Unit & Manual Testing)

While AI tools significantly accelerated development, rigorous human oversight and testing were mandatory to ensure the reliability of the code generated by the Cursor AI agent.

### Unit Testing for AI Contributions
Every time Cursor generated a new component, refactored backend logic, or scaffolded database interactions, the changes were immediately subjected to targeted unit tests.
* **Backend Verification:** We ran `pytest` suites against AI-generated modules (like `security_analyzer.py` and `intent_router.py`) to ensure the logic was sound, variables weren't hallucinated, and state transitions behaved deterministically.
* **Regression Prevention:** Unit testing acted as our first line of defense, ensuring that AI-assisted refactoring didn't accidentally break existing core functionality or routing logic.

### Manual Testing & Usability Validation
Passing unit tests is not enough for user-facing features. All AI-assisted changes underwent strict manual testing.
* **UI/UX Checks:** AI-generated Next.js components (like the Risk Shield) were manually tested across different states (Safe, Warning, High Risk) in the browser to verify Tailwind styling, responsiveness, and frontend event handling.
* **End-to-End (E2E) Walkthrough:** We manually verified the entire workflow to ensure the system's usability matched human expectations:
    1. **Trigger:** The user speaks, "Delete the temp directory."
    2. **Analysis:** The command hits the backend, defaults to `pending_approval`, and the background AI Analyzer successfully flags it.
    3. **UI Feedback:** The Next.js frontend updates instantly, displaying the command alongside an amber warning shield explaining the risk of directory deletion.
    4. **Resolution:** The user speaks, "Approve."
    5. **Execution:** The `IntentRouter` successfully updates the database, the local companion claims the task, and the directory is successfully removed.