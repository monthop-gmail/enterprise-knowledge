"""Provenance and citation construction (§3 lifecycle, §10 response contract).

Every result leaving `knowledge.search` carries provenance. This is not a
presentation concern: an agent that cannot say where an answer came from cannot
be audited, and §27 makes citation part of what the Knowledge Plane owes its
consumers rather than something each agent re-derives.
"""

from __future__ import annotations

from .contracts import Citation, Provenance, RetrievedChunk
from .retrieval import Candidate

__all__ = [
    "build_provenance",
    "build_citation",
    "to_retrieved_chunk",
    "build_resource_id",
    "parse_resource_id",
    "SNIPPET_CHARS",
    "RESOURCE_NAMESPACE_SEPARATOR",
]

SNIPPET_CHARS = 240

# ADR-0033 requires the namespace prefix to be reversible. `:` can do that job
# only because `identity/v1#/$defs/Id` restricts ids to `[a-z0-9_-]`, so the
# separator cannot occur inside either half and splitting on the first one is
# unambiguous. If that pattern ever widens, this choice has to be revisited --
# hence the round-trip test rather than a comment alone.
RESOURCE_NAMESPACE_SEPARATOR = ":"


def build_resource_id(workspace_id: str, document_id: str) -> str:
    """The id `policy/v1.action.resource` expects (ADR-0033).

    The rule: a value the producer holds that is unique *more narrowly* than the
    tenant must carry a namespace, because policy is enforced at tenant level. A
    document id here is unique per `(tenant_id, workspace_id, document_id)` --
    the unique constraint in schema.sql -- so the workspace is what makes it
    tenant-unique, and the workspace is therefore the namespace.

    Granularity is the **document**, not the chunk: policy rules are written
    about documents ("board minutes are restricted"), never about chunk 7 of
    one. The chunk stays addressable through the rest of `Provenance` for any
    rule that ever needs it.

    The tenant is deliberately absent. `resource` is read inside a decision that
    is already scoped to a tenant, so repeating it would widen the id past what
    the contract asks for and invite someone to trust it as a cross-tenant key.
    """
    if not workspace_id or not document_id:
        raise ValueError("a resource id needs both a workspace and a document")
    if RESOURCE_NAMESPACE_SEPARATOR in workspace_id:
        raise ValueError(
            f"workspace_id may not contain {RESOURCE_NAMESPACE_SEPARATOR!r}: "
            "the namespace prefix would stop being reversible (ADR-0033)"
        )
    return f"{workspace_id}{RESOURCE_NAMESPACE_SEPARATOR}{document_id}"


def parse_resource_id(resource_id: str) -> tuple[str, str]:
    """Split a resource id back into `(workspace_id, document_id)`.

    Exists to keep ADR-0033's "the prefix must be reversible" honest: a rule that
    is only asserted in prose is one nobody notices breaking.
    """
    workspace_id, separator, document_id = resource_id.partition(RESOURCE_NAMESPACE_SEPARATOR)
    if not separator or not workspace_id or not document_id:
        raise ValueError(f"not a namespaced resource id: {resource_id!r}")
    return workspace_id, document_id


def build_provenance(candidate: Candidate, ingested_at: str | None = None) -> Provenance:
    return Provenance(
        document_id=candidate.document_id,
        chunk_id=candidate.chunk_id,
        workspace_id=candidate.workspace_id,
        resource_id=build_resource_id(candidate.workspace_id, candidate.document_id),
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
