"""Unit tests for agents/command_builder.py."""
from __future__ import annotations

import shlex
from unittest.mock import patch

import pytest

from agents.command_builder import build_provider_command, normalize_provider


# ==================== normalize_provider ====================


class TestNormalizeProvider:
    def test_cursor_maps_to_cursor(self):
        assert normalize_provider("cursor") == "cursor"

    def test_cursor_agent_maps_to_cursor(self):
        assert normalize_provider("cursor-agent") == "cursor"

    def test_claude_maps_to_claude(self):
        assert normalize_provider("claude") == "claude"

    def test_claude_code_maps_to_claude(self):
        assert normalize_provider("claude-code") == "claude"

    def test_shell_maps_to_shell(self):
        assert normalize_provider("shell") == "shell"

    def test_terminal_maps_to_shell(self):
        assert normalize_provider("terminal") == "shell"

    def test_bash_maps_to_shell(self):
        assert normalize_provider("bash") == "shell"

    def test_none_returns_default_provider(self):
        assert normalize_provider(None) == "claude"

    def test_empty_string_returns_default_provider(self):
        assert normalize_provider("") == "claude"

    def test_unknown_string_returns_default_provider(self):
        assert normalize_provider("unknown-provider") == "claude"

    def test_whitespace_only_returns_default_provider(self):
        assert normalize_provider("   ") == "claude"

    def test_case_insensitive_cursor(self):
        assert normalize_provider("CURSOR") == "cursor"
        assert normalize_provider("Cursor") == "cursor"

    def test_case_insensitive_claude(self):
        assert normalize_provider("CLAUDE") == "claude"
        assert normalize_provider("Claude-Code") == "claude"

    def test_case_insensitive_shell(self):
        assert normalize_provider("BASH") == "shell"
        assert normalize_provider("Terminal") == "shell"

    def test_strips_surrounding_whitespace(self):
        assert normalize_provider("  cursor  ") == "cursor"
        assert normalize_provider("  claude  ") == "claude"


# ==================== build_provider_command ====================


class TestBuildProviderCommand:
    def test_cursor_builds_correct_command(self):
        with patch("agents.command_builder.shutil.which", return_value="/usr/bin/cursor"):
            cmd = build_provider_command(provider="cursor", prompt="fix the bug")
        assert cmd.startswith("/usr/bin/cursor --cli agent -p")
        assert "--output-format text" in cmd
        assert "fix the bug" in cmd

    def test_cursor_falls_back_to_bare_binary_when_not_on_path(self):
        with patch("agents.command_builder.shutil.which", return_value=None):
            cmd = build_provider_command(provider="cursor", prompt="do something")
        assert cmd.startswith("cursor --cli agent -p")

    def test_claude_builds_correct_command(self):
        with patch("agents.command_builder.shutil.which", return_value="/usr/local/bin/claude"):
            cmd = build_provider_command(provider="claude", prompt="add tests")
        assert cmd.startswith("/usr/local/bin/claude -p")
        assert "--dangerously-skip-permissions" in cmd
        assert "add tests" in cmd

    def test_claude_falls_back_to_bare_binary_when_not_on_path(self):
        with patch("agents.command_builder.shutil.which", return_value=None):
            cmd = build_provider_command(provider="claude", prompt="do something")
        assert cmd.startswith("claude -p")

    def test_shell_returns_prompt_unchanged(self):
        raw = "echo hello && ls -la"
        cmd = build_provider_command(provider="shell", prompt=raw)
        assert cmd == raw

    def test_shell_does_not_quote_prompt(self):
        # shell provider passes the prompt as a raw command — no quoting
        raw = "git commit -m 'initial'"
        cmd = build_provider_command(provider="shell", prompt=raw)
        assert cmd == raw

    def test_prompt_with_spaces_is_shell_quoted_for_cursor(self):
        with patch("agents.command_builder.shutil.which", return_value="cursor"):
            cmd = build_provider_command(provider="cursor", prompt="fix the login bug")
        # shlex.quote wraps in single quotes when spaces are present
        assert shlex.quote("fix the login bug") in cmd

    def test_prompt_with_single_quotes_is_shell_quoted_for_claude(self):
        prompt = "it's broken"
        with patch("agents.command_builder.shutil.which", return_value="claude"):
            cmd = build_provider_command(provider="claude", prompt=prompt)
        assert shlex.quote(prompt) in cmd

    def test_prompt_with_double_quotes_is_shell_quoted_for_cursor(self):
        prompt = 'say "hello world"'
        with patch("agents.command_builder.shutil.which", return_value="cursor"):
            cmd = build_provider_command(provider="cursor", prompt=prompt)
        assert shlex.quote(prompt) in cmd

    def test_prompt_with_semicolons_is_shell_quoted_for_claude(self):
        prompt = "step1; step2; step3"
        with patch("agents.command_builder.shutil.which", return_value="claude"):
            cmd = build_provider_command(provider="claude", prompt=prompt)
        assert shlex.quote(prompt) in cmd

    def test_prompt_with_special_chars_does_not_break_shell_safety(self):
        # The quoted form must NOT contain the raw special character outside quotes
        prompt = "rm -rf /; echo pwned"
        with patch("agents.command_builder.shutil.which", return_value="claude"):
            cmd = build_provider_command(provider="claude", prompt=prompt)
        # Confirm the semicolon is inside the quoted argument, not a bare shell separator
        # shlex.quote will wrap the whole thing in single quotes
        quoted = shlex.quote(prompt)
        assert quoted in cmd
