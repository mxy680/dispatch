"""Heuristic fallback tests for command security analyzer (no API key required)."""

import asyncio

from services.security_analyzer import analyze_command_security_heuristic_fallback


def test_heuristic_flags_rm_rf_as_high_risk():
    r = asyncio.run(
        analyze_command_security_heuristic_fallback(
            user_prompt="clean disk",
            normalized_command="rm -rf /tmp/foo",
        )
    )
    assert r["risk_level"] == "HIGH_RISK"


def test_heuristic_ls_is_safe():
    r = asyncio.run(
        analyze_command_security_heuristic_fallback(
            user_prompt="list",
            normalized_command="ls -la",
        )
    )
    assert r["risk_level"] == "SAFE"
