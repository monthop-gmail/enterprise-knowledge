"""enterprise-knowledge -- Knowledge Plane implementation for `agent-platform`.

`agent-platform` owns the contract, the policy semantics and the plane boundary.
This package owns the implementation: ingestion, hybrid retrieval, reranking,
ACL/tenant enforcement, provenance and evaluation, exposed as one canonical call.

    from enterprise_knowledge import KnowledgeService, SearchRequest, resolve_policy

Design rules the layout encodes (ref/hybrid-rag-prompt-review.md §28):

    agent-platform        = contract + governance + plane boundary
    enterprise-knowledge  = knowledge plane implementation
    hybrid RAG            = retrieval engine *inside* this package
    MCP                   = adapter, never the core
    evaluation            = quality gate
    ACL / tenant          = security boundary
"""

from __future__ import annotations

from .config import RetrievalConfig, Settings, configure_logging, load_settings
from .contracts import (
    Citation,
    CrossWorkspaceGrant,
    PolicyContext,
    Principal,
    PrincipalType,
    Provenance,
    RetrievalStage,
    RetrievalStrategy,
    RetrievedChunk,
    SearchRequest,
    SearchResponse,
    TenantScope,
    Timings,
    WorkspaceScope,
)
from .errors import (
    ConfigurationError,
    KnowledgeError,
    PolicyViolation,
    TenantBoundaryViolation,
)
from .security import build_scope_predicate, resolve_policy
from .service import KnowledgeService

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # contract
    "SearchRequest",
    "SearchResponse",
    "RetrievedChunk",
    "Provenance",
    "Citation",
    "Timings",
    "RetrievalStage",
    "RetrievalStrategy",
    "PolicyContext",
    "Principal",
    "PrincipalType",
    "TenantScope",
    "WorkspaceScope",
    "CrossWorkspaceGrant",
    # service
    "KnowledgeService",
    "resolve_policy",
    "build_scope_predicate",
    # config
    "Settings",
    "RetrievalConfig",
    "load_settings",
    "configure_logging",
    # errors
    "KnowledgeError",
    "ConfigurationError",
    "PolicyViolation",
    "TenantBoundaryViolation",
]
