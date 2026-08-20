"""Stage 2: cross-encoder reranking (§7).

Stage 2 re-sorts stage-1 candidates; it can never introduce a document stage 1
did not return, so it is not a security boundary and needs no policy input --
the ACL work already happened in SQL (§4.2).

Its latency must be measured separately from database retrieval (§7, §17), which
is why `rerank()` returns its own elapsed time rather than letting the caller
fold it into a single retrieval number.
"""

from __future__ import annotations

import time
from typing import Protocol

from .contracts import RetrievalStrategy
from .errors import ConfigurationError
from .retrieval import Candidate

__all__ = [
    "Reranker",
    "IdentityReranker",
    "FlashRankReranker",
    "build_reranker",
    "reranker_for_strategy",
]

Scored = tuple[Candidate, float]


class Reranker(Protocol):
    model: str

    def rerank(
        self, query: str, candidates: list[Scored], top_k: int
    ) -> tuple[list[Scored], float]:
        """Return (top_k re-sorted candidates, elapsed_ms)."""


class IdentityReranker:
    """Pass-through: keeps stage-1 order and truncates to `top_k`.

    This is the honest implementation of `RetrievalStrategy.HYBRID` and the
    control arm of the benchmark matrix (§16) -- comparing hybrid against
    hybrid+rerank requires a real "no rerank" path, not a disabled flag.
    """

    model = "identity"

    def rerank(
        self, query: str, candidates: list[Scored], top_k: int
    ) -> tuple[list[Scored], float]:
        start = time.perf_counter()
        result = candidates[:top_k]
        return result, (time.perf_counter() - start) * 1000.0


class FlashRankReranker:
    """Phase 3: `flashrank.Ranker` with ms-marco-TinyBERT-L-2-v2 on ONNX/CPU."""

    def __init__(self, model: str = "ms-marco-TinyBERT-L-2-v2") -> None:
        self.model = model
        self._ranker = None  # lazily loaded; model download happens once

    def rerank(
        self, query: str, candidates: list[Scored], top_k: int
    ) -> tuple[list[Scored], float]:
        raise NotImplementedError(
            "Phase 3: load flashrank.Ranker once at construction (not per call), "
            "score (query, chunk.content) pairs, re-sort descending, take top_k, "
            "and return the measured elapsed_ms"
        )


def build_reranker(name: str, model: str) -> Reranker:
    if name == "identity":
        return IdentityReranker()
    if name == "flashrank":
        return FlashRankReranker(model=model)
    raise ConfigurationError(f"unknown reranker {name!r}: expected 'identity' or 'flashrank'")


def reranker_for_strategy(strategy: RetrievalStrategy, configured: Reranker) -> Reranker:
    """Stage 2 runs only for HYBRID_RERANK; the other arms use pass-through."""
    if strategy is RetrievalStrategy.HYBRID_RERANK:
        return configured
    return IdentityReranker()
