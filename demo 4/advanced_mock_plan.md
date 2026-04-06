# Advanced Mock-Object Test Plan (Demo 4)
## Feature A: AI Security Analyzer

### Code under test

- `server/services/security_analyzer.py`
- `server/main.py` (`_background_security_scan`)

### Mock strategy

- Mock the external LLM call at the OpenAI/Groq client boundary.
- Return deterministic JSON payloads:
  - `SAFE`
  - `WARNING`
  - `HIGH_RISK`
- Assert:
  - JSON is parsed correctly
  - normalized risk fields are persisted via `models.update_command_risk_assessment(...)`

### Failure-path test

- Mock timeout/exception from LLM call.
- Assert fallback classifier runs and the command remains in a safe, reviewable state (no crash).

## Feature B: Voice Approval Intent Router

### Code under test

- `server/main.py` (`_is_affirmation_intent`, `_classify_reply`, `/api/unified/reply`)

### Mock strategy

- Mock database/model functions (`get_conversation_state`, `get_terminal_command`, `update_terminal_command_for_approval`, etc.).
- Feed spoken intents (`"yes"`, `"approve"`, `"yes?"`, `"no"`).
- Assert:
  - approve intent attempts transition `pending_approval -> queued`
  - reject intent attempts transition `pending_approval -> cancelled`
  - high-risk commands block voice-approve path and return expected API error

## Execution commands

```bash
cd server
python -m pytest tests/test_security_analyzer.py tests/test_api_endpoints.py -q
```
