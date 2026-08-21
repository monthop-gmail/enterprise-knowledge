"""Canonical types for the Knowledge Plane.

Ref: ref/hybrid-rag-prompt-review.md  §10 (Canonical Service), §17 (Latency
Breakdown), §27 (agents only know `knowledge.search`).

This module is the Python **projection** of the platform's contracts, not their
source. `agent-platform` owns the wire schema and stores it as YAML + JSON Schema
only (ADR-0008); it cannot import Python, so nothing here is shipped to it. Each
consumer repo writes or generates its own types from the same central schema --
this file is ours.

It is deliberately **stdlib-only** so that any code translating to or from the
contract can import it without pulling in a database driver, a model SDK or a
transport library. Adapters translate to/from these types -- they never invent
their own response shape (§11).

Vocabulary lock (ADR-0017): the one who *acts* is the **actor**; `subject` means
*what the record is about* and must never be used for the caller. The distinction
matters more here than almost anywhere else -- ACL-aware retrieval is precisely
the question of which documents *about other people* this actor may see -- and
Python has no schema validator to catch the swap, so the guard is the naming.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "Principal",
    "PrincipalType",
    "TenantScope",
    "PolicyContext",
    "MetadataFilter",
    "SearchRequest",
    "Provenance",
    "Citation",
    "RetrievedChunk",
    "SearchResponse",
    "RetrievalStage",
    "Timings",
    "RetrievalStrategy",
]


# ---------------------------------------------------------------------------
# Identity / policy  (§4.2, §4.3)
# ---------------------------------------------------------------------------


class PrincipalType(StrEnum):
    """`identity/v1#/$defs/Principal.type` -- required by the platform contract."""

    HUMAN = "human"
    AGENT = "agent"
    SERVICE = "service"


@dataclass(frozen=True, slots=True)
class Principal:
    """The actor: who is asking.

    Supplied by the platform's identity plane, never by the caller. Projection of
    `identity/v1#/$defs/Principal`, whose required fields are `type` and `id`.

    `roles`/`groups`/`attributes` are local to this repo -- the platform contract
    does not carry them, and they exist only to feed the ACL scope. Keep them out
    of anything serialised onto the wire.
    """

    principal_id: str  # -> identity/v1 `id` (ActorId)
    type: PrincipalType = PrincipalType.HUMAN
    display_name: str | None = None
    # Delegation chain: an agent acting for a human. ADR-0007/identity-v1 rule --
    # delegation must never widen what the originating principal could see. The
    # enforcement belongs in resolve_policy() (#16); this field only models it.
    on_behalf_of: Principal | None = None
    roles: frozenset[str] = frozenset()
    groups: frozenset[str] = frozenset()
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TenantScope:
    """Hard multi-tenant boundary (§4.3).

    There is intentionally no "all tenants" value. A cross-tenant read is a new
    request per tenant, not a widened scope.
    """

    tenant_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.tenant_id.strip():
            raise ValueError("tenant_id is required: the tenant boundary is not optional")


@dataclass(frozen=True, slots=True)
class PolicyContext:
    """Resolved authorization scope for one search.

    Produced by the security layer *before* retrieval and carried into the SQL
    pre-filter. §4.2 forbids the "retrieve everything, then filter" shape, so
    this object is an input to retrieval and never a post-processing step.
    """

    tenant: TenantScope
    principal: Principal
    # Metadata keys/values the principal is allowed to see, e.g.
    # {"classification": ["public", "internal"]}. Empty dict = no extra ACL
    # narrowing beyond the tenant boundary.
    allowed_metadata: dict[str, list[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

# Caller-supplied narrowing, applied as JSONB containment (`metadata @> ...`).
# Distinct from PolicyContext: filters are a *preference*, policy is a *rule*.
MetadataFilter = dict[str, Any]


class RetrievalStrategy(StrEnum):
    """The three strategies the benchmark matrix compares (§16)."""

    DENSE = "dense"
    HYBRID = "hybrid"
    HYBRID_RERANK = "hybrid_rerank"


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Input to `knowledge.search`."""

    query: str
    policy: PolicyContext
    filters: MetadataFilter = field(default_factory=dict)
    top_k: int | None = None  # None -> config default (final_k)
    strategy: RetrievalStrategy = RetrievalStrategy.HYBRID_RERANK


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a chunk came from. Required on every result (§10, §3 lifecycle)."""

    document_id: str
    chunk_id: str
    source: str | None = None
    chunk_index: int = 0
    ingested_at: str | None = None  # ISO-8601


@dataclass(frozen=True, slots=True)
class Citation:
    """Renderable reference an agent or app can show to a human."""

    label: str
    document_id: str
    chunk_id: str
    source: str | None = None
    snippet: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """One retrieved chunk with its scores at each stage."""

    content: str
    metadata: dict[str, Any]
    provenance: Provenance
    citation: Citation
    # Final score the consumer should rank on: rerank score when stage 2 ran,
    # otherwise the fused RRF score.
    score: float
    rrf_score: float | None = None
    dense_rank: int | None = None
    sparse_rank: int | None = None
    rerank_score: float | None = None


class RetrievalStage(StrEnum):
    STAGE_1_CANDIDATES = "stage_1_candidates"
    STAGE_2_RERANKED = "stage_2_reranked"


@dataclass(frozen=True, slots=True)
class Timings:
    """Latency breakdown (§17).

    Reported in milliseconds and always split -- §25 forbids folding generation
    time into retrieval time or reporting e2e alone.
    """

    dense_ms: float = 0.0
    sparse_ms: float = 0.0
    rrf_ms: float = 0.0
    rerank_ms: float = 0.0
    retrieval_total_ms: float = 0.0
    generation_ms: float | None = None
    e2e_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class SearchResponse:
    """Output of `knowledge.search`.

    `documents` is the post-stage-2 result set. `candidates` keeps the stage-1
    output so evaluation can score both stages independently (§15).
    """

    query: str
    documents: list[RetrievedChunk]
    timings: Timings
    strategy: RetrievalStrategy
    tenant_id: str
    candidates: list[RetrievedChunk] = field(default_factory=list)
    stage: RetrievalStage = RetrievalStage.STAGE_2_RERANKED
