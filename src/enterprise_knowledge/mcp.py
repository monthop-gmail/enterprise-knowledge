"""MCP adapter (§11, §12, §19).

MCP is a transport, not the architecture (§4.1). The tool exposed here is a
translation of `knowledge.search`, so it must not accept a parameter the
canonical contract does not have, and must not return a shape the contract does
not define (§11).

**stdout integrity (§12).** In stdio transport, stdout carries JSON-RPC frames
and nothing else. No `print()`, no library that logs to stdout, no progress bar.
`configure_logging()` pins every handler to stderr; `tests/mcp/` asserts the
stream stays clean across a real session.

Identity note: `tenant_id`, `workspace_id` and `principal_id` arrive from the
platform's session context, never from a model-authored tool argument --
otherwise an agent could name its own tenant and the §4.3 boundary would be
advisory (Phase 9). The same holds for `workspace_id`: widening past the home
workspace is a policy decision (ADR-0021), and a tool argument is not one.
"""

from __future__ import annotations

from typing import Any

from .contracts import SearchResponse
from .service import KnowledgeService

__all__ = ["TOOL_NAME", "build_mcp_server", "response_to_tool_payload"]

TOOL_NAME = "search_company_knowledge"


def response_to_tool_payload(response: SearchResponse) -> dict[str, Any]:
    """Serialise a `SearchResponse` for the wire, preserving the §10 field names."""
    return {
        "query": response.query,
        "tenant_id": response.tenant_id,
        "strategy": response.strategy.value,
        "documents": [
            {
                "content": doc.content,
                "score": doc.score,
                "metadata": doc.metadata,
                "document_id": doc.provenance.document_id,
                "chunk_id": doc.provenance.chunk_id,
                "source": doc.provenance.source,
                "provenance": {
                    "document_id": doc.provenance.document_id,
                    "chunk_id": doc.provenance.chunk_id,
                    "chunk_index": doc.provenance.chunk_index,
                    "source": doc.provenance.source,
                    "ingested_at": doc.provenance.ingested_at,
                },
                "citation": {
                    "label": doc.citation.label,
                    "source": doc.citation.source,
                    "snippet": doc.citation.snippet,
                },
            }
            for doc in response.documents
        ],
        "timings_ms": {
            "dense": response.timings.dense_ms,
            "sparse": response.timings.sparse_ms,
            "rrf": response.timings.rrf_ms,
            "rerank": response.timings.rerank_ms,
            "retrieval_total": response.timings.retrieval_total_ms,
            "e2e": response.timings.e2e_ms,
        },
    }


def build_mcp_server(service: KnowledgeService) -> Any:
    """Phase 5: FastMCP server exposing `search_company_knowledge`.

    Tool signature (an adapter of `knowledge.search`, §11):

        search_company_knowledge(
            query: str,
            department: str | None = None,
            document_type: str | None = None,
            final_k: int = 2,
        )

    `department`/`document_type` map onto `SearchRequest.filters` -- both are
    labels, not scopes (ADR-0007). Tenant, workspace and principal come from
    session context, not from these arguments.
    """
    raise NotImplementedError(
        "Phase 5: construct FastMCP, register TOOL_NAME, resolve PolicyContext from "
        "session identity (tenant + workspace + principal), call service.search(), "
        "return response_to_tool_payload(). "
        "Call configure_logging() before serving so nothing touches stdout."
    )
