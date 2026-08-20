"""Error taxonomy for the Knowledge Plane."""

from __future__ import annotations

__all__ = [
    "KnowledgeError",
    "ConfigurationError",
    "PolicyViolation",
    "TenantBoundaryViolation",
    "StorageError",
    "EmbeddingError",
    "RerankError",
]


class KnowledgeError(Exception):
    """Base for everything this package raises."""


class ConfigurationError(KnowledgeError):
    """Invalid or missing configuration."""


class PolicyViolation(KnowledgeError):
    """A request was refused by the security layer.

    §26: unauthorized retrieval is a failure even when the answer is correct.
    Adapters must surface this as a refusal, never as an empty result set --
    "no results" and "not allowed" are different answers.
    """


class TenantBoundaryViolation(PolicyViolation):
    """A query would have crossed the hard tenant boundary (§4.3)."""


class StorageError(KnowledgeError):
    """Database/pool failure."""


class EmbeddingError(KnowledgeError):
    """Embedding provider failure."""


class RerankError(KnowledgeError):
    """Stage 2 reranker failure."""
