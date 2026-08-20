"""Benchmark harness: the quality gate (§16, §17, §18).

Every ground-truth case is run through all three arms:

    A. dense only
    B. dense + FTS + RRF
    C. dense + FTS + RRF + FlashRank

reporting Hit@K, Recall@K, MRR, metadata leakage and a p50/p95 latency
breakdown per stage. Comparing B against C is the whole point -- it is the only
way to show the reranker earns its latency (§15).

Two modes (§18):

* **offline** -- fixture corpus, deterministic embedder, identity reranker, no
  network. Runs in CI on every change; catches algorithm regressions for free.
* **integration** -- live PostgreSQL + pgvector, real embeddings, real
  FlashRank, real MCP. Production-like, run deliberately.

Offline numbers are comparable only to other offline numbers: the deterministic
embedder has no semantic behaviour, so its absolute Hit@K says nothing about
production retrieval quality.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from enterprise_knowledge.contracts import RetrievalStrategy

from .ground_truth import GROUND_TRUTH, GroundTruthCase
from .metrics import LatencySummary

__all__ = ["CaseResult", "ArmResult", "BenchmarkReport", "run_benchmark", "main"]

ARMS: tuple[RetrievalStrategy, ...] = (
    RetrievalStrategy.DENSE,
    RetrievalStrategy.HYBRID,
    RetrievalStrategy.HYBRID_RERANK,
)


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    retrieved_stage1: tuple[str, ...]
    retrieved_stage2: tuple[str, ...]
    hit_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    leaked: int
    retrieval_ms: float
    rerank_ms: float


@dataclass(frozen=True, slots=True)
class ArmResult:
    """Aggregate for one strategy across every case."""

    strategy: RetrievalStrategy
    hit_at_k: float
    recall_at_k: float
    mrr: float
    total_leaked: int
    latency: LatencySummary
    cases: tuple[CaseResult, ...] = ()

    @property
    def passed(self) -> bool:
        """Leakage is a hard gate: quality metrics cannot buy it back (§26)."""
        return self.total_leaked == 0


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    mode: str
    k: int
    arms: dict[RetrievalStrategy, ArmResult] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(arm.passed for arm in self.arms.values())


def run_benchmark(
    mode: str = "offline",
    k: int = 3,
    cases: tuple[GroundTruthCase, ...] = GROUND_TRUTH,
) -> BenchmarkReport:
    """Phase 6/7."""
    raise NotImplementedError(
        "Phase 6/7: build a KnowledgeService for `mode`, ingest FIXTURE_CORPUS "
        "(offline) or assert the live index (integration), run every case through "
        "ARMS via service.with_strategy(), and aggregate with evaluation.metrics. "
        "Fail the run on any leakage before reporting quality numbers."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchmark")
    parser.add_argument("--mode", choices=("offline", "integration"), default="offline")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args(argv)
    report = run_benchmark(mode=args.mode, k=args.k)
    return 0 if report.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
