"""
Tests for database/sidecar_store.py.

Uses a real in-memory SQLite path via DISPATCH_SIDECAR_PATH env var
so no mocking is needed — the store is purely local.
"""
from __future__ import annotations

import os
import tempfile
import pytest
from database import sidecar_store as store


@pytest.fixture(autouse=True)
def tmp_sidecar(tmp_path, monkeypatch):
    """Point the sidecar store at a fresh temp file for each test."""
    db_path = tmp_path / "test_sidecar.db"
    monkeypatch.setenv("DISPATCH_SIDECAR_PATH", str(db_path))
    yield


# ---------------------------------------------------------------------------
# add_conversation_turn / list_conversation_turns_for_user
# ---------------------------------------------------------------------------

class TestConversationTurns:
    def test_add_turn_returns_row_with_expected_fields(self):
        row = store.add_conversation_turn(
            user_id="u1", project_id="p1", session_id="s1",
            command_id="c1", role="assistant", turn_type="approval_request",
            content="Please approve this command",
        )
        assert row["user_id"] == "u1"
        assert row["role"] == "assistant"
        assert row["content"] == "Please approve this command"
        assert "id" in row
        assert "created_at" in row

    def test_list_turns_returns_added_turn(self):
        store.add_conversation_turn(
            user_id="u1", project_id="p1", session_id=None,
            command_id=None, role="user", turn_type="command",
            content="Run tests",
        )
        turns = store.list_conversation_turns_for_user(user_id="u1")
        assert len(turns) == 1
        assert turns[0]["content"] == "Run tests"

    def test_list_turns_filtered_by_project(self):
        store.add_conversation_turn(
            user_id="u1", project_id="p1", session_id=None,
            command_id=None, role="user", turn_type="command", content="for p1",
        )
        store.add_conversation_turn(
            user_id="u1", project_id="p2", session_id=None,
            command_id=None, role="user", turn_type="command", content="for p2",
        )
        turns = store.list_conversation_turns_for_user(user_id="u1", project_id="p1")
        assert len(turns) == 1
        assert turns[0]["content"] == "for p1"

    def test_list_turns_empty_for_unknown_user(self):
        turns = store.list_conversation_turns_for_user(user_id="nobody")
        assert turns == []

    def test_turns_returned_in_chronological_order(self):
        for i in range(3):
            store.add_conversation_turn(
                user_id="u1", project_id="p1", session_id=None,
                command_id=None, role="user", turn_type="command",
                content=f"msg {i}",
            )
        turns = store.list_conversation_turns_for_user(user_id="u1")
        assert turns[0]["content"] == "msg 0"
        assert turns[2]["content"] == "msg 2"


# ---------------------------------------------------------------------------
# conversation state upsert / get
# ---------------------------------------------------------------------------

class TestConversationState:
    def test_get_state_returns_none_when_missing(self):
        result = store.get_conversation_state(user_id="u1", project_id="p1")
        assert result is None

    def test_upsert_state_and_get_returns_row(self):
        store.upsert_conversation_state(
            user_id="u1", project_id="p1",
            state="awaiting_approval", active_command_id="cmd-1",
        )
        result = store.get_conversation_state(user_id="u1", project_id="p1")
        assert result["state"] == "awaiting_approval"
        assert result["active_command_id"] == "cmd-1"

    def test_upsert_overwrites_existing_state(self):
        store.upsert_conversation_state(
            user_id="u1", project_id="p1",
            state="awaiting_approval", active_command_id="cmd-1",
        )
        store.upsert_conversation_state(
            user_id="u1", project_id="p1",
            state="idle", active_command_id=None,
        )
        result = store.get_conversation_state(user_id="u1", project_id="p1")
        assert result["state"] == "idle"
        assert result["active_command_id"] is None

    def test_upsert_stores_context_json(self):
        store.upsert_conversation_state(
            user_id="u1", project_id="p1",
            state="idle", active_command_id=None,
            context_json={"key": "value"},
        )
        result = store.get_conversation_state(user_id="u1", project_id="p1")
        assert result is not None

    def test_none_project_id_works(self):
        store.upsert_conversation_state(
            user_id="u1", project_id=None,
            state="idle", active_command_id=None,
        )
        result = store.get_conversation_state(user_id="u1", project_id=None)
        assert result["state"] == "idle"


# ---------------------------------------------------------------------------
# command risk set / get / enrich
# ---------------------------------------------------------------------------

class TestCommandRisk:
    def test_set_and_get_command_risk(self):
        store.set_command_risk(
            command_id="cmd-1", user_id="u1",
            risk_level="HIGH_RISK", risk_reason="rm -rf detected",
            plain_summary="This is dangerous.",
        )
        result = store.get_command_risk("cmd-1")
        assert result["risk_level"] == "HIGH_RISK"
        assert result["risk_reason"] == "rm -rf detected"
        assert result["plain_summary"] == "This is dangerous."

    def test_get_command_risk_returns_none_for_unknown(self):
        assert store.get_command_risk("nonexistent") is None

    def test_set_command_risk_normalizes_invalid_level(self):
        store.set_command_risk(
            command_id="cmd-2", user_id="u1",
            risk_level="GARBAGE", risk_reason=None,
        )
        result = store.get_command_risk("cmd-2")
        assert result["risk_level"] == "WARNING"

    def test_set_command_risk_upserts_on_conflict(self):
        store.set_command_risk(
            command_id="cmd-3", user_id="u1",
            risk_level="SAFE", risk_reason="looks fine",
        )
        store.set_command_risk(
            command_id="cmd-3", user_id="u1",
            risk_level="WARNING", risk_reason="changed mind",
        )
        result = store.get_command_risk("cmd-3")
        assert result["risk_level"] == "WARNING"

    def test_reset_command_risk_pending(self):
        store.set_command_risk(
            command_id="cmd-4", user_id="u1",
            risk_level="HIGH_RISK", risk_reason="bad",
        )
        store.reset_command_risk_pending(command_id="cmd-4", user_id="u1")
        result = store.get_command_risk("cmd-4")
        assert result["risk_level"] == "PENDING"

    def test_enrich_command_adds_risk_fields(self):
        store.set_command_risk(
            command_id="cmd-5", user_id="u1",
            risk_level="SAFE", risk_reason="benign",
            plain_summary="All good.",
        )
        cmd = {"id": "cmd-5", "command": "ls -la"}
        enriched = store.enrich_command(cmd)
        assert enriched["risk_level"] == "SAFE"
        assert enriched["risk_reason"] == "benign"

    def test_enrich_command_returns_pending_when_no_risk_set(self):
        cmd = {"id": "cmd-unknown", "command": "ls"}
        enriched = store.enrich_command(cmd)
        assert enriched["risk_level"] == "PENDING"

    def test_enrich_command_none_returns_none(self):
        assert store.enrich_command(None) is None

    def test_enrich_commands_list(self):
        store.set_command_risk(
            command_id="cmd-6", user_id="u1",
            risk_level="WARNING", risk_reason="curl",
        )
        cmds = [{"id": "cmd-6", "command": "curl x.com"}, {"id": "cmd-99", "command": "ls"}]
        result = store.enrich_commands(cmds)
        assert result[0]["risk_level"] == "WARNING"
        assert result[1]["risk_level"] == "PENDING"
