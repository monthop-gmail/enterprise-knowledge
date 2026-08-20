"""`knowledge.search` -- the canonical service (§10, §11, §13, §27).

This is the only entry point consumers get. Agents and applications know this
call and nothing else: not PostgreSQL, not pgvector, not RRF, not FlashRank
(§27). Adapters (MCP, Direct/LCEL, and any future REST or SDK surface) translate
transport to `SearchRequest` and back -- they never re-implement the pipeline and
never add a parameter that is not in the contract (§11).

Retrieval is deliberately generation-free (§13): nothing in this module calls an
LLM, so retrieval can be benchmarked without one and generation latency can
never contaminate retrieval latency (§17, §25).
"""

from __future__ import annotations

import time
from dataclasses import replace

from .config import Settings
from .contracts import (
    MetadataFilter,
    PolicyContext,
    RetrievalStage,
    RetrievalStrategy,
    SearchRequest,
    SearchResponse,
    Timings,
)
from .embeddings import Embedder
from .provenance import to_retrieved_chunk
from .reranker import Reranker, reranker_for_strategy
from .retrieval import HybridRetriever

__all__ = ["KnowledgeService"]


class KnowledgeService:
    """Orchestrates: embed -> stage 1 (scoped) -> stage 2 -> provenance."""

    def __init__(
        self,
        settings: Settings,
        embedder: Embedder,
        retriever: HybridRetriever,
        reranker: Reranker,
    ) -> None:
        self.settings = settings
        self.embedder = embedder
        self.retriever = retriever
        self.reranker = reranker

    # -- canonical entry point ------------------------------------------------

    def search(self, request: SearchRequest) -> SearchResponse:
        """Run one scoped search and return results with provenance and timings.

        Raises `PolicyViolation` rather than returning an empty list when the
        request is refused -- "nothing matched" and "you may not ask that" must
        stay distinguishable to the caller.
        """
        cfg = self.settings.retrieval
        top_k = request.top_k or cfg.final_k
        t0 = time.perf_counter()

        query_vector = self.embedder.embed_query(request.query)

        # The retriever builds the scope predicate from `request.policy` itself,
        # so there is no path into SQL that skips the ACL pre-filter (§4.2).
        fused, ranked_lists = self.retriever.retrieve(
            query=request.query,
            query_vector=query_vector,
            policy=request.policy,
            filters=request.filters,
        )
        retrieval_done = time.perf_counter()

        dense = ranked_lists.get("dense")
        sparse = ranked_lists.get("sparse")
        dense_ranks = dense.ranks() if dense else {}
        sparse_ranks = sparse.ranks() if sparse else {}

        candidates = [
            to_retrieved_chunk(
                cand,
                score=rrf,
                rrf_score=rrf,
                dense_rank=dense_ranks.get(cand.chunk_id),
                sparse_rank=sparse_ranks.get(cand.chunk_id),
            )
            for cand, rrf in fused
        ]

        stage2 = reranker_for_strategy(request.strategy, self.reranker)
        reranked, rerank_ms = stage2.rerank(request.query, fused, top_k)

        documents = [
            to_retrieved_chunk(
                cand,
                score=score,
                rrf_score=next((r for c, r in fused if c.chunk_id == cand.chunk_id), None),
                dense_rank=dense_ranks.get(cand.chunk_id),
                sparse_rank=sparse_ranks.get(cand.chunk_id),
                rerank_score=score if request.strategy is RetrievalStrategy.HYBRID_RERANK else None,
            )
            for cand, score in reranked
        ]

        e2e_ms = (time.perf_counter() - t0) * 1000.0
        timings = Timings(
            dense_ms=dense.elapsed_ms if dense else 0.0,
            sparse_ms=sparse.elapsed_ms if sparse else 0.0,
            # Whatever stage 1 spent that was not dense or sparse retrieval:
            # fusion plus row mapping.
            rrf_ms=max(
                0.0,
                (retrieval_done - t0) * 1000.0
                - (dense.elapsed_ms if dense else 0.0)
                - (sparse.elapsed_ms if sparse else 0.0),
            ),
            rerank_ms=rerank_ms,
            retrieval_total_ms=(retrieval_done - t0) * 1000.0 + rerank_ms,
            generation_ms=None,  # retrieval never generates (§13)
            e2e_ms=e2e_ms,
        )

        return SearchResponse(
            query=request.query,
            documents=documents,
            candidates=candidates,
            timings=timings,
            strategy=request.strategy,
            tenant_id=request.policy.tenant.tenant_id,
            stage=(
                RetrievalStage.STAGE_2_RERANKED
                if request.strategy is RetrievalStrategy.HYBRID_RERANK
                else RetrievalStage.STAGE_1_CANDIDATES
            ),
        )

    # -- convenience ----------------------------------------------------------

    def search_scoped(
        self,
        query: str,
        policy: PolicyContext,
        filters: MetadataFilter | None = None,
        top_k: int | None = None,
        strategy: RetrievalStrategy = RetrievalStrategy.HYBRID_RERANK,
    ) -> SearchResponse:
        """Keyword form of `search` for call sites that do not build a request."""
        return self.search(
            SearchRequest(
                query=query,
                policy=policy,
                filters=dict(filters or {}),
                top_k=top_k,
                strategy=strategy,
            )
        )

    def with_strategy(self, request: SearchRequest, strategy: RetrievalStrategy) -> SearchResponse:
        """Re-run a request under a different arm of the benchmark matrix (§16)."""
        return self.search(replace(request, strategy=strategy))
