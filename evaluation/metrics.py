"""Retrieval metrics (§15, §17).

Pure functions over ranked document-id lists -- no database, no model, no I/O --
so they are unit-testable and identical between the offline and integration
benchmarks (§18).

Every metric takes a *ranked* list, best first, and treats rank 1 as the top
result, matching the RRF rank base in §6.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

__all__ = [
    "hit_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "mean_reciprocal_rank",
    "metadata_leakage",
    "percentile",
    "LatencySummary",
    "summarize_latency",
]


def hit_at_k(retrieved: Sequence[str], expected: Iterable[str], k: int) -> float:
    """1.0 if any expected document appears in the top-k, else 0.0."""
    if k < 1:
        raise ValueError("k must be >= 1")
    expected_set = set(expected)
    return 1.0 if expected_set & set(retrieved[:k]) else 0.0


def recall_at_k(retrieved: Sequence[str], expected: Iterable[str], k: int) -> float:
    """Fraction of expected documents present in the top-k.

    Returns 0.0 for an empty expectation rather than 1.0: a case with nothing to
    find cannot be evidence that retrieval works, and averaging in a free 1.0
    would quietly inflate the suite.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    expected_set = set(expected)
    if not expected_set:
        return 0.0
    found = expected_set & set(retrieved[:k])
    return len(found) / len(expected_set)


def reciprocal_rank(retrieved: Sequence[str], expected: Iterable[str]) -> float:
    """1/rank of the first expected document, or 0.0 if none is retrieved."""
    expected_set = set(expected)
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in expected_set:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(cases: Iterable[tuple[Sequence[str], Iterable[str]]]) -> float:
    values = [reciprocal_rank(r, e) for r, e in cases]
    return sum(values) / len(values) if values else 0.0


def metadata_leakage(retrieved: Sequence[str], denied: Iterable[str]) -> int:
    """Count of results the scope should have made unreachable.

    This is a **gate, not a score** (§26): any value above zero fails the run,
    however good Hit@K looks. It is reported as a count so a regression shows how
    many documents leaked, not merely that something did.
    """
    denied_set = set(denied)
    return sum(1 for doc_id in retrieved if doc_id in denied_set)


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile; `q` in [0, 1]. p50/p95 per §16."""
    if not values:
        return 0.0
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be within [0, 1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[int(pos)]
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


@dataclass(frozen=True, slots=True)
class LatencySummary:
    count: int
    p50_ms: float
    p95_ms: float
    mean_ms: float


def summarize_latency(samples: Sequence[float]) -> LatencySummary:
    return LatencySummary(
        count=len(samples),
        p50_ms=percentile(samples, 0.50),
        p95_ms=percentile(samples, 0.95),
        mean_ms=(sum(samples) / len(samples)) if samples else 0.0,
    )
