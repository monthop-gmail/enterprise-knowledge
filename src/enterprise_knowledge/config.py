"""Runtime configuration, resolved from environment (§6, §7, §9).

Every retrieval knob named in §6 is configurable and carries the documented
default. Nothing here reaches out to a network or a database -- config is a
plain value object so tests can construct one directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .errors import ConfigurationError

__all__ = ["RetrievalConfig", "Settings", "load_settings", "configure_logging"]


@dataclass(frozen=True, slots=True)
class RetrievalConfig:
    """Canonical retrieval configuration (§6).

    RRF is part of the contract, not an implementation detail: `rrf_k` and the
    rank base of 1 are fixed semantics that `agent-platform` may assert on.
    """

    dense_k: int = 10
    sparse_k: int = 10
    candidate_k: int = 10
    final_k: int = 3
    rrf_k: int = 60
    hnsw_ef_search: int = 40

    def __post_init__(self) -> None:
        for name in ("dense_k", "sparse_k", "candidate_k", "final_k", "rrf_k", "hnsw_ef_search"):
            if getattr(self, name) < 1:
                raise ConfigurationError(f"{name} must be >= 1")
        if self.final_k > self.candidate_k:
            raise ConfigurationError(
                f"final_k ({self.final_k}) cannot exceed candidate_k ({self.candidate_k}): "
                "stage 2 re-sorts stage 1 output, it cannot invent candidates"
            )


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = "postgresql://ek:ek@localhost:55433/enterprise_knowledge"
    pool_min_size: int = 1
    pool_max_size: int = 8

    embedder: str = "deterministic"  # deterministic | openai
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    openai_api_key: str | None = None

    reranker: str = "identity"  # identity | flashrank
    rerank_model: str = "ms-marco-TinyBERT-L-2-v2"

    chat_model: str = "gpt-4o-mini"
    chat_temperature: float = 0.0

    log_level: str = "INFO"
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from exc


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build Settings from the process environment (or an explicit mapping)."""
    if env is not None:
        os.environ.update(env)

    settings = Settings(
        database_url=os.getenv("EK_DATABASE_URL", Settings.database_url),
        pool_min_size=_int("EK_POOL_MIN_SIZE", 1),
        pool_max_size=_int("EK_POOL_MAX_SIZE", 8),
        embedder=os.getenv("EK_EMBEDDER", "deterministic"),
        embedding_model=os.getenv("EK_EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_dim=_int("EK_EMBEDDING_DIM", 1536),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        reranker=os.getenv("EK_RERANKER", "identity"),
        rerank_model=os.getenv("EK_RERANK_MODEL", "ms-marco-TinyBERT-L-2-v2"),
        chat_model=os.getenv("EK_CHAT_MODEL", "gpt-4o-mini"),
        chat_temperature=float(os.getenv("EK_CHAT_TEMPERATURE", "0") or 0),
        log_level=os.getenv("EK_LOG_LEVEL", "INFO"),
        retrieval=RetrievalConfig(
            dense_k=_int("EK_DENSE_K", 10),
            sparse_k=_int("EK_SPARSE_K", 10),
            candidate_k=_int("EK_CANDIDATE_K", 10),
            final_k=_int("EK_FINAL_K", 3),
            rrf_k=_int("EK_RRF_K", 60),
            hnsw_ef_search=_int("EK_HNSW_EF_SEARCH", 40),
        ),
    )
    if settings.embedder == "openai" and not settings.openai_api_key:
        raise ConfigurationError("EK_EMBEDDER=openai requires OPENAI_API_KEY")
    return settings


def configure_logging(settings: Settings) -> None:
    """Route all logging to **stderr** (§12).

    stdout belongs to MCP JSON-RPC. A single stray handler on stdout corrupts the
    protocol stream, so this is set once, centrally, and never overridden per
    module -- and `tests/mcp/` asserts stdout stays clean.
    """
    import logging
    import sys

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
