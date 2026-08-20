"""RRF is canonical behaviour (§6), so it is pinned by exact-value tests."""

from __future__ import annotations

import pytest

from enterprise_knowledge.retrieval import Candidate, RankedList, RRFFuser


def cand(chunk_id: str) -> Candidate:
    return Candidate(chunk_id=chunk_id, content=chunk_id, metadata={}, document_id=chunk_id)


def test_formula_matches_spec_exactly() -> None:
    dense = RankedList("dense", [cand("a"), cand("b")])
    sparse = RankedList("sparse", [cand("b"), cand("a")])
    fused = {c.chunk_id: s for c, s in RRFFuser(60).fuse([dense, sparse], limit=10)}

    # a: rank 1 dense + rank 2 sparse; b: rank 2 dense + rank 1 sparse -> equal.
    assert fused["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)


def test_rank_base_is_one_not_zero() -> None:
    only = RankedList("dense", [cand("a")])
    (_, score), = RRFFuser(60).fuse([only], limit=1)
    assert score == pytest.approx(1 / 61), "rank must start at 1 (§6), not 0"


def test_missing_from_a_list_contributes_nothing() -> None:
    dense = RankedList("dense", [cand("a")])
    sparse = RankedList("sparse", [cand("b"), cand("c")])
    fused = {c.chunk_id: s for c, s in RRFFuser(60).fuse([dense, sparse], limit=10)}

    # 'a' appears in one list only: its score is that single contribution, with
    # no penalty term for the list it is absent from.
    assert fused["a"] == pytest.approx(1 / 61)
    assert fused["b"] == pytest.approx(1 / 61)
    assert fused["c"] == pytest.approx(1 / 62)

    # Were absence scored as "ranked last", 'a' (absent from a 2-item list)
    # would have picked up 1/62 on top and overtaken 'b'.
    assert fused["a"] < 1 / 61 + 1 / 62


def test_ties_break_deterministically() -> None:
    dense = RankedList("dense", [cand("x"), cand("y")])
    sparse = RankedList("sparse", [cand("y"), cand("x")])
    first = [c.chunk_id for c, _ in RRFFuser(60).fuse([dense, sparse], limit=2)]
    again = [c.chunk_id for c, _ in RRFFuser(60).fuse([dense, sparse], limit=2)]
    assert first == again == ["x", "y"]


def test_limit_applies_after_fusion() -> None:
    dense = RankedList("dense", [cand(c) for c in "abcde"])
    assert len(RRFFuser(60).fuse([dense], limit=2)) == 2


def test_rrf_k_must_be_positive() -> None:
    with pytest.raises(ValueError):
        RRFFuser(0)
