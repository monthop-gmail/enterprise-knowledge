"""The drift checker's parser (no network).

The fetching half is exercised by the scheduled workflow against the real
repository. What is worth pinning here is the parser: a check that silently
reads fewer pins than the file lists would report "no drift" while checking
almost nothing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "check_contract_drift", ROOT / "scripts" / "check_contract_drift.py"
)
assert SPEC and SPEC.loader
drift = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drift)


def test_reads_every_pin_in_the_real_file() -> None:
    repo, pins = drift.read_pins((ROOT / "platform-contract.yaml").read_text(encoding="utf-8"))
    assert repo == "monthop-gmail/agent-platform"
    # If a contract is added to the file, it must show up here -- silently
    # checking six of seven is the failure this test exists to prevent.
    assert set(pins) == {
        "identity/v1",
        "policy/v1",
        "event/v1",
        "consent/v1",
        "error/v1",
        "tool/v1",
        "mcp/v1",
    }
    assert all(p.count(".") == 2 for p in pins.values())


def test_comments_and_blank_lines_are_ignored() -> None:
    text = """
platform:
  repo: owner/repo  # trailing comment

contracts:
  a/v1:
    version: 1.2.3
    used_for: something

  # a commented-out contract must not be counted
  b/v1:
    version: 0.1.0
"""
    repo, pins = drift.read_pins(text)
    assert repo == "owner/repo"
    assert pins == {"a/v1": "1.2.3", "b/v1": "0.1.0"}


def test_a_file_with_no_pins_is_an_error_not_an_empty_pass() -> None:
    with pytest.raises(SystemExit):
        drift.read_pins("platform:\n  repo: owner/repo\n")


def test_version_heading_matches_the_changelog_shape() -> None:
    changelog = "# error/v1\n\n## v1.1.0 — 2026-09-10\n"
    assert drift.VERSION_HEADING.search(changelog).group(1) == "1.1.0"
