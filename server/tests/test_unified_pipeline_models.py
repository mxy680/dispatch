from database import models
from agents.command_builder import build_provider_command, normalize_provider


def test_provider_preference_roundtrip(test_db):
    user_id = "user-1"
    models.set_default_provider_for_user(user_id, "claude")
    assert models.get_default_provider_for_user(user_id) == "claude"

    models.set_default_provider_for_user(user_id, "unknown")
    assert models.get_default_provider_for_user(user_id) == "cursor"


def test_terminal_access_roundtrip(test_db):
    user_id = "user-1"
    models.set_terminal_access_for_user(user_id, True)
    assert models.get_terminal_access_for_user(user_id) is True
    models.set_terminal_access_for_user(user_id, False)
    assert models.get_terminal_access_for_user(user_id) is False


def test_create_terminal_command_with_metadata(test_db):
    project_id = models.create_project("user-1", "Proj")
    session_id = models.create_terminal_session(
        user_id="user-1",
        project_id=project_id,
        name="Unified Session",
        instance_id=None,
    )
    command_id = models.create_terminal_command(
        session_id=session_id,
        user_id="user-1",
        command="echo hello",
        source="voice",
        provider="claude",
        user_prompt="say hello",
        normalized_command="echo hello",
    )
    cmd = models.get_terminal_command(command_id)
    assert cmd is not None
    assert cmd["source"] == "voice"
    assert cmd["provider"] == "claude"
    assert cmd["user_prompt"] == "say hello"
    assert cmd["normalized_command"] == "echo hello"


def test_get_or_create_terminal_session_for_project_reuses(test_db):
    project_id = models.create_project("user-1", "Proj")
    first = models.get_or_create_terminal_session_for_project(
        user_id="user-1",
        project_id=project_id,
        name="Unified Session",
    )
    second = models.get_or_create_terminal_session_for_project(
        user_id="user-1",
        project_id=project_id,
        name="Unified Session",
    )
    assert first["id"] == second["id"]


def test_list_recent_terminal_commands_for_user(test_db):
    project_id = models.create_project("user-1", "Proj")
    session_id = models.create_terminal_session(
        user_id="user-1",
        project_id=project_id,
        name="Unified Session",
        instance_id=None,
    )
    models.create_terminal_command(session_id=session_id, user_id="user-1", command="pwd")
    rows = models.list_recent_terminal_commands_for_user(user_id="user-1", limit=10)
    assert len(rows) == 1
    assert rows[0]["project_id"] == project_id
    assert rows[0]["project_name"] == "Proj"


def test_command_builder_provider_templates():
    assert normalize_provider("CLAUDE") == "claude"
    assert normalize_provider("n/a") == "cursor"
    assert normalize_provider("copilot") == "cursor"
    cursor_cmd = build_provider_command(provider="cursor", prompt="refactor")
    assert "agent -p " in cursor_cmd
    assert "CI=1" in cursor_cmd
    assert "claude -p " in build_provider_command(provider="claude", prompt="fix tests")
    assert build_provider_command(provider="shell", prompt="ls -la") == "ls -la"

from database import models


class TestProjectUpsert:
    def test_upsert_project_by_name_creates_and_updates_path(self, test_db):
        p1 = models.upsert_project_by_name(user_id="user-1", name="Workspace", file_path="/tmp/a")
        assert p1["id"] is not None
        assert p1["file_path"] == "/tmp/a"

        p2 = models.upsert_project_by_name(user_id="user-1", name="Workspace", file_path="/tmp/b")
        assert p2["id"] == p1["id"]
        assert p2["file_path"] == "/tmp/b"


class TestAgentTokens:
    def test_create_and_resolve_agent_token(self, test_db):
        token_row = models.create_agent_token(user_id="user-1", label="Laptop")
        token_id = token_row["token_id"]
        token = token_row["token"]
        assert token_id and token

        user_id = models.get_user_id_for_agent_token(token)
        assert user_id == "user-1"

        tokens = models.list_agent_tokens(user_id="user-1")
        assert any(t["id"] == token_id for t in tokens)

        models.revoke_agent_token(user_id="user-1", token_id=token_id)
        assert models.get_user_id_for_agent_token(token) is None


class TestTerminalClaim:
    def test_claim_next_returns_session_scoped_command(self, test_db):
        pid = models.create_project("user-1", "Proj")
        inst = models.register_instance(user_id="user-1", project_id=pid, instance_token="abc", status="online")
        sid = models.create_terminal_session(
            user_id="user-1",
            project_id=pid,
            name="Main",
            instance_id=inst["id"],
            status="active",
        )
        cid = models.create_terminal_command(session_id=sid, user_id="user-1", command="ls")

        claimed = models.claim_next_queued_command_for_instance(instance_id=inst["id"])
        assert claimed is not None
        assert claimed["id"] == cid
        assert claimed["session_id"] == sid

