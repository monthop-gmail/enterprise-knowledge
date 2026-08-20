"""Provenance and citation construction (§3 lifecycle, §10 response contract).

Every result leaving `knowledge.search` carries provenance. This is not a
presentation concern: an agent that cannot say where an answer came from cannot
be audited, and §27 makes citation part of what the Knowledge Plane owes its
consumers rather than something each agent re-derives.
"""

from __future__ import annotations

from .contracts import Citation, Provenance, RetrievedChunk
from .retrieval import Candidate

__all__ = ["build_provenance", "build_citation", "to_retrieved_chunk", "SNIPPET_CHARS"]

SNIPPET_CHARS = 240


def build_provenance(candidate: Candidate, ingested_at: str | None = None) -> Provenance:
    return Provenance(
        document_id=candidate.document_id,
        chunk_id=candidate.chunk_id,
        source=candidate.source,
        chunk_index=candidate.chunk_index,
        ingested_at=ingested_at,
    )


def build_citation(candidate: Candidate, snippet_chars: int = SNIPPET_CHARS) -> Citation:
    """Human-facing reference.

    The label prefers a metadata title and falls back to the document id, so a
    citation is never empty even for a source that carried no title.
    """
    title = candidate.metadata.get("title") or candidate.source or candidate.document_id
    label = f"{title}#{candidate.chunk_index}" if candidate.chunk_index else str(title)
    snippet = candidate.content.strip()
    if len(snippet) > snippet_chars:
        snippet = snippet[:snippet_chars].rstrip() + "…"
    return Citation(
        label=label,
        document_id=candidate.document_id,
        chunk_id=candidate.chunk_id,
        source=candidate.source,
        snippet=snippet,
    )


def to_retrieved_chunk(
    candidate: Candidate,
    *,
    score: float,
    rrf_score: float | None = None,
    dense_rank: int | None = None,
    sparse_rank: int | None = None,
    rerank_score: float | None = None,
) -> RetrievedChunk:
    """Assemble the public result object from an internal candidate."""
    return RetrievedChunk(
        content=candidate.content,
        metadata=dict(candidate.metadata),
        provenance=build_provenance(candidate),
        citation=build_citation(candidate),
        score=score,
        rrf_score=rrf_score,
        dense_rank=dense_rank,
        sparse_rank=sparse_rank,
        rerank_score=rerank_score,
    )
