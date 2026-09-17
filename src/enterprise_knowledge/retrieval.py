"""Stage 1: dense + sparse candidate retrieval fused by RRF (§5, §6, §9).

Layering:

    DenseRetriever ─┐
                    ├─> RRFFuser ─> candidate_k ─> HybridRetriever
    SparseRetriever ┘

`RRFFuser` is implemented here rather than stubbed: §6 declares RRF canonical
behaviour that `agent-platform` may assert on, so the formula, the rank base and
the tie-break belong to the contract, not to a backend.

The SQL retrievers are Phase 2 work. Their shape is fixed here so the security
property survives implementation: the scope predicate from `security.py` is
spliced into *each CTE's* WHERE clause, never applied afterwards (§4.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import RetrievalConfig
from .contracts import MetadataFilter, PolicyContext
from .security import ScopePredicate, build_scope_predicate

__all__ = [
    "Candidate",
    "RankedList",
    "RRFFuser",
    "DenseRetriever",
    "SparseRetriever",
    "HybridRetriever",
    "SqlHybridRetriever",
    "build_stage1_sql",
    "build_stage1_params",
]


@dataclass(frozen=True, slots=True)
class Candidate:
    """A stage-1 hit before fusion."""

    chunk_id: str
    content: str
    metadata: dict[str, Any]
    document_id: str
    # Required, not defaulted: a chunk with no workspace cannot be given a
    # tenant-unique resource id, and provenance is not optional (§10).
    workspace_id: str
    chunk_index: int = 0
    source: str | None = None
    raw_score: float = 0.0  # cosine distance (dense) or ts_rank_cd (sparse)


@dataclass(slots=True)
class RankedList:
    """One retriever's output, ordered best-first. Rank 1 is the first element (§6)."""

    name: str
    candidates: list[Candidate] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def ranks(self) -> dict[str, int]:
        return {c.chunk_id: i + 1 for i, c in enumerate(self.candidates)}


class RRFFuser:
    """Reciprocal Rank Fusion (§6).

        score(d) = sum over lists of 1 / (rrf_k + rank(d, list))

    Ranks are 1-based. A document missing from a list contributes nothing for
    that list -- it is not treated as ranked last, which would let list length
    silently reweight the fusion.
    """

    def __init__(self, rrf_k: int = 60) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be >= 1")
        self.rrf_k = rrf_k

    def fuse(self, lists: list[RankedList], limit: int) -> list[tuple[Candidate, float]]:
        scores: dict[str, float] = {}
        best: dict[str, Candidate] = {}
        # Deterministic tie-break: first appearance across lists, in list order.
        order: dict[str, int] = {}

        for ranked in lists:
            for rank, cand in enumerate(ranked.candidates, start=1):
                scores[cand.chunk_id] = scores.get(cand.chunk_id, 0.0) + 1.0 / (self.rrf_k + rank)
                best.setdefault(cand.chunk_id, cand)
                order.setdefault(cand.chunk_id, len(order))

        fused = sorted(scores.items(), key=lambda kv: (-kv[1], order[kv[0]]))
        return [(best[cid], score) for cid, score in fused[:limit]]

    def rank_map(self, lists: list[RankedList]) -> dict[str, dict[str, int]]:
        """Per-list rank of each chunk, for the `dense_rank`/`sparse_rank` fields."""
        return {ranked.name: ranked.ranks() for ranked in lists}


class DenseRetriever(Protocol):
    """HNSW cosine search over `embedding` (§5)."""

    def search(
        self,
        query_vector: list[float],
        scope: ScopePredicate,
        k: int,
        ef_search: int,
    ) -> RankedList: ...


class SparseRetriever(Protocol):
    """PostgreSQL full-text search ranked by `ts_rank_cd` (§5)."""

    def search(self, query: str, scope: ScopePredicate, k: int) -> RankedList: ...


class HybridRetriever(Protocol):
    """Stage 1 as a whole: dense + sparse + pre-filter + RRF -> candidate_k."""

    def retrieve(
        self,
        query: str,
        query_vector: list[float],
        policy: PolicyContext,
        filters: MetadataFilter | None = None,
    ) -> tuple[list[tuple[Candidate, float]], dict[str, RankedList]]: ...


def build_stage1_sql(scope: ScopePredicate) -> str:
    """The single parameterised stage-1 statement (§5).

    Returned as text so it can be reviewed and asserted on before the driver
    exists. Two CTEs, each carrying the *same* scope predicate, fused in SQL.

    Bind order follows placeholder order exactly:

        dense CTE  : vector, vector, *scope.params, vector, dense_k
        sparse CTE : query, query, *scope.params, query, sparse_k
        fused CTE  : rrf_k, rrf_k
        outer      : candidate_k

    `build_stage1_params()` assembles this so no call site has to count `%s`.

    §9: the caller must run this inside a transaction that has already issued
    `SET LOCAL hnsw.ef_search`, so the setting cannot leak back into the pool.
    """
    return f"""
WITH dense AS (
    SELECT id, content, metadata, document_id, workspace_id, chunk_index, source,
           embedding <=> %s::vector AS distance,
           ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) AS rank
    FROM langchain_hybrid_docs
    WHERE {scope.sql}
      AND embedding IS NOT NULL
    ORDER BY embedding <=> %s::vector
    LIMIT %s
),
sparse AS (
    SELECT id, content, metadata, document_id, workspace_id, chunk_index, source,
           ts_rank_cd(tsv_content, plainto_tsquery('english', %s)) AS rank_score,
           ROW_NUMBER() OVER (
               ORDER BY ts_rank_cd(tsv_content, plainto_tsquery('english', %s)) DESC
           ) AS rank
    FROM langchain_hybrid_docs
    WHERE {scope.sql}
      AND tsv_content @@ plainto_tsquery('english', %s)
    ORDER BY rank_score DESC
    LIMIT %s
),
fused AS (
    SELECT COALESCE(d.id, s.id) AS id,
           COALESCE(d.content, s.content) AS content,
           COALESCE(d.metadata, s.metadata) AS metadata,
           COALESCE(d.document_id, s.document_id) AS document_id,
           COALESCE(d.workspace_id, s.workspace_id) AS workspace_id,
           COALESCE(d.chunk_index, s.chunk_index) AS chunk_index,
           COALESCE(d.source, s.source) AS source,
           d.rank AS dense_rank,
           s.rank AS sparse_rank,
           COALESCE(1.0 / (%s + d.rank), 0.0) + COALESCE(1.0 / (%s + s.rank), 0.0) AS rrf_score
    FROM dense d
    FULL OUTER JOIN sparse s ON d.id = s.id
)
SELECT * FROM fused
ORDER BY rrf_score DESC, id
LIMIT %s
"""


class SqlHybridRetriever:
    """Phase 2: `HybridRetriever` backed by PostgreSQL + pgvector."""

    def __init__(self, storage: Any, config: RetrievalConfig) -> None:
        self.storage = storage
        self.config = config
        self.fuser = RRFFuser(config.rrf_k)

    def retrieve(
        self,
        query: str,
        query_vector: list[float],
        policy: PolicyContext,
        filters: MetadataFilter | None = None,
    ) -> tuple[list[tuple[Candidate, float]], dict[str, RankedList]]:
        # Built here (not by the caller) so no code path can reach the database
        # without a scope predicate attached.
        scope = build_scope_predicate(policy, filters)
        _sql = build_stage1_sql(scope)
        raise NotImplementedError(
            "Phase 2: execute _sql inside storage.retrieval_transaction() and map "
            "rows to Candidate; fusion may come from SQL or RRFFuser, but both must "
            "agree with the §6 formula (see tests/unit/test_rrf.py)"
        )


def build_stage1_params(
    scope: ScopePredicate,
    query: str,
    query_vector: list[float],
    config: RetrievalConfig,
) -> tuple[Any, ...]:
    """Bind values for `build_stage1_sql`, in placeholder order.

    Kept next to the SQL so the two move together; `tests/unit/test_stage1_sql.py`
    asserts the count matches the number of `%s` in the statement.
    """
    vec = query_vector
    return (
        vec, vec, *scope.params, vec, config.dense_k,
        query, query, *scope.params, query, config.sparse_k,
        config.rrf_k, config.rrf_k,
        config.candidate_k,
    )
