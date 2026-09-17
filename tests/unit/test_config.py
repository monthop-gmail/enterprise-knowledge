"""Settings and RetrievalConfig behaviour (§6, §9)."""

from __future__ import annotations

import pytest

from enterprise_knowledge.config import (
    DEFAULT_DATABASE_URL,
    RetrievalConfig,
    Settings,
    load_settings,
)
from enterprise_knowledge.errors import ConfigurationError


def test_default_database_url_is_a_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: `Settings` uses slots, so reading a default off the *class*
    returns the slot descriptor rather than the value.

    `load_settings()` used to do exactly that, producing a Settings whose
    `database_url` was a descriptor object. Nothing failed until something tried
    to connect, and then the error named neither config nor the real cause.
    """
    monkeypatch.delenv("EK_DATABASE_URL", raising=False)
    settings = load_settings()
    assert isinstance(settings.database_url, str)
    assert settings.database_url == Settings().database_url == DEFAULT_DATABASE_URL


def test_env_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EK_DATABASE_URL", "postgresql://x:y@example:5432/db")
    assert load_settings().database_url == "postgresql://x:y@example:5432/db"


def test_empty_env_value_falls_back_to_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unset variable and one set to "" mean the same thing to a shell."""
    monkeypatch.setenv("EK_DATABASE_URL", "")
    assert load_settings().database_url == DEFAULT_DATABASE_URL


def test_retrieval_defaults_match_the_spec() -> None:
    """§6 pins these; agent-platform may assert on them."""
    cfg = RetrievalConfig()
    actual = (cfg.dense_k, cfg.sparse_k, cfg.candidate_k, cfg.final_k, cfg.rrf_k)
    assert actual == (10, 10, 10, 3, 60)
    assert cfg.hnsw_ef_search == 40


def test_non_integer_env_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EK_FINAL_K", "three")
    with pytest.raises(ConfigurationError):
        load_settings()


def test_openai_embedder_without_a_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EK_EMBEDDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        load_settings()
