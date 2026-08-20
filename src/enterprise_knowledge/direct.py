"""Direct adapter: `knowledge.search` + LCEL generation (§13).

Two responsibilities, kept apart on purpose:

* `DirectKnowledgeClient` -- in-process access to the canonical service. No LLM
  involved, so development and the retrieval benchmark can use it freely.
* `LcelAnswerer` -- optional generation on top of retrieved context.

§13 requires the split: retrieval must be benchmarkable without calling an LLM,
and §25 forbids reporting generation latency as retrieval latency. Anything that
needs an answer composes the two; nothing inside retrieval reaches for the model.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import MetadataFilter, PolicyContext, RetrievalStrategy, SearchResponse
from .service import KnowledgeService

__all__ = ["DirectKnowledgeClient", "LcelAnswerer", "GeneratedAnswer"]


class DirectKnowledgeClient:
    """Thin in-process adapter. Deliberately adds nothing to the contract."""

    def __init__(self, service: KnowledgeService) -> None:
        self.service = service

    def search(
        self,
        query: str,
        policy: PolicyContext,
        filters: MetadataFilter | None = None,
        top_k: int | None = None,
        strategy: RetrievalStrategy = RetrievalStrategy.HYBRID_RERANK,
    ) -> SearchResponse:
        return self.service.search_scoped(query, policy, filters, top_k, strategy)


@dataclass(frozen=True, slots=True)
class GeneratedAnswer:
    """An answer plus the citations it was grounded in, and split timings."""

    answer: str
    retrieval: SearchResponse
    generation_ms: float


class LcelAnswerer:
    """Phase 5: ChatPromptTemplate | ChatOpenAI(gpt-4o-mini, temperature=0) | StrOutputParser."""

    def __init__(self, service: KnowledgeService) -> None:
        self.service = service

    def answer(
        self,
        query: str,
        policy: PolicyContext,
        filters: MetadataFilter | None = None,
        top_k: int | None = None,
    ) -> GeneratedAnswer:
        raise NotImplementedError(
            "Phase 5: call service.search_scoped() first, build context from the "
            "returned chunks, then run the LCEL chain. Time the chain separately "
            "and report it as generation_ms -- never add it to retrieval_total_ms"
        )
