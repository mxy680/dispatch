"""
Tests for:
  - agents/copilot_agent.py
  - agents/prompt_refiner.py
  - services/llm.py
  - database/supabase_client.py (get_sb error path)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# agents/prompt_refiner.py
# ---------------------------------------------------------------------------

class TestPromptRefiner:
    def test_create_project_intent(self):
        from agents.prompt_refiner import refine_prompt
        result = refine_prompt({"intent": "create_project", "project_name": "MyApp"})
        assert "MyApp" in result
        assert "New Project" in result

    def test_create_task_intent(self):
        from agents.prompt_refiner import refine_prompt
        result = refine_prompt({
            "intent": "create_task",
            "project_name": "MyApp",
            "task_description": "Add login page",
        })
        assert "MyApp" in result
        assert "Add login page" in result

    def test_fix_bug_intent(self):
        from agents.prompt_refiner import refine_prompt
        result = refine_prompt({
            "intent": "fix_bug",
            "project_name": "MyApp",
            "task_description": "Fix null pointer",
        })
        assert "Fix null pointer" in result
        assert "Bug Fix" in result

    def test_status_check_intent(self):
        from agents.prompt_refiner import refine_prompt
        result = refine_prompt({"intent": "status_check", "project_name": "MyApp"})
        assert "Status" in result

    def test_unknown_intent_uses_fallback(self):
        from agents.prompt_refiner import refine_prompt
        result = refine_prompt({"intent": "unknown", "task_description": "do something"})
        assert "do something" in result

    def test_unrecognized_intent_uses_unknown_template(self):
        from agents.prompt_refiner import refine_prompt
        result = refine_prompt({"intent": "teleport", "task_description": "beam me up"})
        assert "beam me up" in result

    def test_missing_fields_use_defaults(self):
        from agents.prompt_refiner import refine_prompt
        result = refine_prompt({"intent": "create_task"})
        assert "Unknown" in result
        assert "No description" in result

    def test_returns_string(self):
        from agents.prompt_refiner import refine_prompt
        result = refine_prompt({})
        assert isinstance(result, str) and result


# ---------------------------------------------------------------------------
# agents/copilot_agent.py
# ---------------------------------------------------------------------------

class TestCopilotAgent:
    def test_dispatch_task_returns_stub_status(self):
        from agents.copilot_agent import dispatch_task
        result = dispatch_task("task-1", {"intent": "create_task"}, False)
        assert result["status"] == "stub"
        assert result["task_id"] == "task-1"

    def test_dispatch_task_includes_task_id(self):
        from agents.copilot_agent import dispatch_task
        result = dispatch_task("task-xyz", {}, True)
        assert result["task_id"] == "task-xyz"

    def test_set_terminal_access_calls_supabase(self):
        mock_sb = MagicMock()
        with patch("agents.copilot_agent.get_sb", return_value=mock_sb):
            from agents.copilot_agent import set_terminal_access
            set_terminal_access("user-1", True)
        mock_sb.table.assert_called_with("user_preferences")

    def test_get_terminal_access_returns_true_when_granted(self):
        mock_res = MagicMock()
        mock_res.data = {"terminal_access": True}
        mock_chain = MagicMock()
        mock_chain.execute.return_value = mock_res
        mock_chain.select.return_value = mock_chain
        mock_chain.eq.return_value = mock_chain
        mock_chain.maybe_single.return_value = mock_chain
        mock_sb = MagicMock()
        mock_sb.table.return_value = mock_chain

        with patch("agents.copilot_agent.get_sb", return_value=mock_sb):
            from agents.copilot_agent import get_terminal_access
            result = get_terminal_access("user-1")
        assert result is True

    def test_get_terminal_access_returns_false_when_not_set(self):
        mock_res = MagicMock()
        mock_res.data = None
        mock_chain = MagicMock()
        mock_chain.execute.return_value = mock_res
        mock_chain.select.return_value = mock_chain
        mock_chain.eq.return_value = mock_chain
        mock_chain.maybe_single.return_value = mock_chain
        mock_sb = MagicMock()
        mock_sb.table.return_value = mock_chain

        with patch("agents.copilot_agent.get_sb", return_value=mock_sb):
            from agents.copilot_agent import get_terminal_access
            result = get_terminal_access("user-1")
        assert result is False


# ---------------------------------------------------------------------------
# services/llm.py
# ---------------------------------------------------------------------------

class TestLLM:
    def test_get_client_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        import services.llm as llm
        llm._client = None
        with pytest.raises(RuntimeError, match="GROQ_API_KEY is not set"):
            llm._get_client()

    def test_get_client_returns_client_with_key(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        import services.llm as llm
        llm._client = None
        with patch("services.llm.AsyncOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            client = llm._get_client()
        assert client is not None
        llm._client = None

    async def test_parse_intent_returns_parsed_json(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        import services.llm as llm

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"intent": "create_task", "project_name": "MyApp"}'

        mock_completions = AsyncMock()
        mock_completions.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.chat.completions = mock_completions
        llm._client = mock_client

        result = await llm.parse_intent("add a login page", [{"name": "MyApp"}])
        assert result["intent"] == "create_task"
        assert result["project_name"] == "MyApp"
        llm._client = None

    async def test_parse_intent_returns_error_on_exception(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        import services.llm as llm

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API down"))
        llm._client = mock_client

        result = await llm.parse_intent("do something", [])
        assert result["intent"] == "error"
        llm._client = None

    async def test_parse_intent_strips_markdown_fence(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        import services.llm as llm

        mock_response = MagicMock()
        mock_response.choices[0].message.content = '```json\n{"intent": "status_check"}\n```'

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        llm._client = mock_client

        result = await llm.parse_intent("status", [])
        assert result["intent"] == "status_check"
        llm._client = None


# ---------------------------------------------------------------------------
# database/supabase_client.py
# ---------------------------------------------------------------------------

class TestSupabaseClient:
    def test_get_sb_raises_when_env_not_set(self, monkeypatch):
        import database.supabase_client as sc
        monkeypatch.setattr(sc, "SUPABASE_URL", "")
        monkeypatch.setattr(sc, "SUPABASE_SERVICE_ROLE_KEY", "")
        sc._client = None
        with pytest.raises(RuntimeError, match="SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"):
            sc.get_sb()
        sc._client = None

    def test_get_sb_returns_cached_client(self, monkeypatch):
        import database.supabase_client as sc
        fake_client = MagicMock()
        sc._client = fake_client
        result = sc.get_sb()
        assert result is fake_client
        sc._client = None
