"""Ingestion pipeline: parse -> classify -> chunk -> embed -> index (§3, §14).

Ingestion is the only writer of `langchain_hybrid_docs`. It is also where the
tenant boundary is established: a chunk without a tenant cannot be written, so
no later retrieval can accidentally expose one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .contracts import TenantScope, WorkspaceScope
from .embeddings import Embedder
from .storage import Storage

__all__ = ["SourceDocument", "Chunk", "Parser", "Chunker", "Ingestor", "PostgresIngestor"]


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """A document as it arrives from a connector (GitHub, Odoo, files, web...)."""

    document_id: str
    text: str
    tenant: TenantScope
    workspace: WorkspaceScope
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable unit, ready to embed and index."""

    document_id: str
    chunk_index: int
    content: str
    tenant_id: str
    workspace_id: str
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Parser(Protocol):
    """Bytes/blob -> SourceDocument. One implementation per connector."""

    def parse(
        self, blob: bytes, *, tenant: TenantScope, workspace: WorkspaceScope, **kwargs: Any
    ) -> SourceDocument: ...


class Chunker(Protocol):
    """SourceDocument -> chunks. Chunk boundaries decide retrieval granularity."""

    def chunk(self, document: SourceDocument) -> list[Chunk]: ...


class Ingestor(Protocol):
    def ingest(self, documents: Iterable[SourceDocument]) -> int:
        """Index documents; returns the number of chunks written."""


class PostgresIngestor:
    """Phase 1: chunk -> embed -> upsert into `langchain_hybrid_docs`.

    Upsert keys on `(tenant_id, workspace_id, document_id, chunk_index)` -- the
    unique constraint in schema.sql -- so re-ingesting a changed document replaces
    its chunks rather than duplicating them (§3: Feedback -> Re-index). The same
    `document_id` in two workspaces is two documents, not one with a conflict.
    """

    def __init__(self, storage: Storage, embedder: Embedder, chunker: Chunker) -> None:
        self.storage = storage
        self.embedder = embedder
        self.chunker = chunker

    def ingest(self, documents: Iterable[SourceDocument]) -> int:
        raise NotImplementedError(
            "Phase 1: chunk each document, batch-embed the chunks, and upsert with "
            "ON CONFLICT (tenant_id, workspace_id, document_id, chunk_index) DO UPDATE"
        )
