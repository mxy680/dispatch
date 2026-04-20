"""
Property-based tests using Hypothesis.

These complement the example-based tests in test_security_analyzer.py and
test_command_builder.py by generating thousands of arbitrary inputs and
asserting invariants that must hold for *any* input, not just the ones we
thought to write down.

Three modules under test:
  - services/security_analyzer._normalize_level
  - agents/command_builder.normalize_provider
  - agents/command_builder.build_provider_command
"""

from __future__ import annotations

import shlex

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from services.security_analyzer import _normalize_level, VALID_LEVELS
from agents.command_builder import normalize_provider, build_provider_command

VALID_PROVIDERS = {"cursor", "claude", "shell"}


# ---------------------------------------------------------------------------
# _normalize_level — output is always a known risk level
# ---------------------------------------------------------------------------

class TestNormalizeLevelProperties:
    @given(st.text())
    def test_output_always_in_valid_levels(self, s: str):
        """For any string input, _normalize_level returns a known risk level."""
        result = _normalize_level(s)
        assert result in VALID_LEVELS

    @given(st.sampled_from(sorted(VALID_LEVELS)))
    def test_valid_level_is_identity(self, level: str):
        """A string that is already a valid level passes through unchanged."""
        assert _normalize_level(level) == level

    @given(st.sampled_from(sorted(VALID_LEVELS)))
    def test_lowercase_valid_level_normalizes(self, level: str):
        """Lowercase versions of valid levels are accepted."""
        assert _normalize_level(level.lower()) == level

    @given(st.text(min_size=1))
    def test_output_is_non_empty_string(self, s: str):
        result = _normalize_level(s)
        assert isinstance(result, str) and result


# ---------------------------------------------------------------------------
# normalize_provider — output is always a known provider
# ---------------------------------------------------------------------------

class TestNormalizeProviderProperties:
    @given(st.text())
    def test_output_always_in_valid_providers(self, s: str):
        """For any string input, normalize_provider returns a known provider."""
        result = normalize_provider(s)
        assert result in VALID_PROVIDERS

    @given(st.none() | st.just(""))
    def test_empty_or_none_returns_default(self, s):
        """None and empty string both produce the default provider."""
        assert normalize_provider(s) == "claude"

    @given(st.text())
    def test_output_is_non_empty_string(self, s: str):
        result = normalize_provider(s)
        assert isinstance(result, str) and result


# ---------------------------------------------------------------------------
# build_provider_command — structural invariants
# ---------------------------------------------------------------------------

# Hypothesis printable text, excluding null bytes which shlex can't handle
_prompt_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
    max_size=500,
)


class TestBuildProviderCommandProperties:
    @given(_prompt_text)
    def test_shell_provider_returns_prompt_verbatim(self, prompt: str):
        """shell provider passes the prompt through without modification."""
        assert build_provider_command(provider="shell", prompt=prompt) == prompt

    @given(_prompt_text)
    def test_claude_command_contains_prompt(self, prompt: str):
        """The user's prompt always appears (shell-quoted) inside the claude command."""
        cmd = build_provider_command(provider="claude", prompt=prompt)
        assert shlex.quote(prompt) in cmd

    @given(_prompt_text)
    def test_cursor_command_contains_prompt(self, prompt: str):
        """The user's prompt always appears (shell-quoted) inside the cursor command."""
        cmd = build_provider_command(provider="cursor", prompt=prompt)
        assert shlex.quote(prompt) in cmd

    @given(_prompt_text)
    def test_claude_command_contains_flag(self, prompt: str):
        """`-p` flag is always present in the claude command."""
        cmd = build_provider_command(provider="claude", prompt=prompt)
        assert "-p " in cmd

    @given(_prompt_text)
    def test_cursor_command_contains_flag(self, prompt: str):
        """Cursor-specific flags are always present."""
        cmd = build_provider_command(provider="cursor", prompt=prompt)
        assert "--cli" in cmd
        assert "-p " in cmd

    @given(st.sampled_from(sorted(VALID_PROVIDERS)), _prompt_text)
    def test_command_is_always_a_string(self, provider: str, prompt: str):
        """build_provider_command always returns a str regardless of provider."""
        result = build_provider_command(provider=provider, prompt=prompt)
        assert isinstance(result, str)
