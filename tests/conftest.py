"""Shared fixtures. Keeps `src/` importable without an editable install."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import pytest  # noqa: E402

from enterprise_knowledge.contracts import Principal  # noqa: E402
from enterprise_knowledge.security import resolve_policy  # noqa: E402


@pytest.fixture
def principal() -> Principal:
    return Principal(principal_id="u-1", roles=frozenset({"staff"}))


@pytest.fixture
def policy(principal: Principal):
    return resolve_policy("acme", principal, {"classification": ["public", "internal"]})


@pytest.fixture
def database_url() -> str | None:
    """Live database for integration tests, or None to skip them."""
    return os.getenv("EK_DATABASE_URL")
