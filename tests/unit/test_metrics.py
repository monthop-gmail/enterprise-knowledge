"""Metric semantics (§15). These numbers gate every later performance claim."""

from __future__ import annotations

import pytest
from evaluation.metrics import (
    hit_at_k,
    mean_reciprocal_rank,
    metadata_leakage,
    percentile,
    recall_at_k,
    reciprocal_rank,
    summarize_latency,
)


def test_hit_at_k_respects_the_cutoff() -> None:
    assert hit_at_k(["x", "a"], ["a"], k=1) == 0.0
    assert hit_at_k(["x", "a"], ["a"], k=2) == 1.0


def test_recall_at_k_is_a_fraction_of_expected() -> None:
    assert recall_at_k(["a", "b", "z"], ["a", "b", "c"], k=3) == pytest.approx(2 / 3)


def test_recall_with_no_expectation_is_zero_not_one() -> None:
    # A case with nothing to find must not silently inflate the suite average.
    assert recall_at_k(["a"], [], k=3) == 0.0


def test_reciprocal_rank_uses_first_hit() -> None:
    assert reciprocal_rank(["x", "y", "a"], ["a", "y"]) == pytest.approx(1 / 2)
    assert reciprocal_rank(["x"], ["a"]) == 0.0


def test_mrr_averages_cases() -> None:
    cases = [(["a"], ["a"]), (["x", "b"], ["b"])]
    assert mean_reciprocal_rank(cases) == pytest.approx((1.0 + 0.5) / 2)


def test_metadata_leakage_counts_every_offender() -> None:
    assert metadata_leakage(["a", "secret", "secret2"], ["secret", "secret2"]) == 2
    assert metadata_leakage(["a"], ["secret"]) == 0


def test_percentile_endpoints_and_interpolation() -> None:
    values = [10.0, 20.0, 30.0, 40.0]
    assert percentile(values, 0.0) == 10.0
    assert percentile(values, 1.0) == 40.0
    assert percentile(values, 0.5) == pytest.approx(25.0)
    assert percentile([], 0.5) == 0.0


def test_latency_summary_reports_p50_and_p95() -> None:
    summary = summarize_latency([5.0, 6.0, 7.0, 100.0])
    assert summary.count == 4
    assert summary.p50_ms == pytest.approx(6.5)
    assert summary.p95_ms > summary.p50_ms
