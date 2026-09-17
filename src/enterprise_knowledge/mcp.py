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

__all__ = [
    "TOOL_NAME",
    "TOOL_CONTRACT_VERSION",
    "TOOL_DESCRIPTION",
    "build_mcp_server",
    "response_to_tool_payload",
]

# Already lowercase `[a-z0-9_]`, so ADR-0027's transformation is the identity
# here. The namespace segment it prepends (`mcp/v1 server_id`) is added by
# whoever registers the tool, not by this constant -- a ToolId assembled here
# would be wrong the moment the same tool is served from a second server.
TOOL_NAME = "search_company_knowledge"

# ADR-0028: a tool response is a contract whose version announcement never
# reaches the caller reliably, because the tool description is cached on the
# client for an unknown length of time. The rules that follow from that:
#
#   * within a major, keys may be added -- never removed, renamed, or given a
#     new meaning
#   * a superseded key stays alongside its replacement until the next major
#   * the integer appears in *two* places that are cached differently -- the
#     first line of the tool description (stale on the client) and a top-level
#     key of each freshly built result (always current)
#
# The second copy is what makes a mismatch diagnosable: a caller comparing the
# two can tell it is holding a stale description instead of guessing.
TOOL_CONTRACT_VERSION = 1

TOOL_DESCRIPTION = f"""contract {TOOL_CONTRACT_VERSION}
Search the organisation's knowledge and return passages with provenance and
citations. Results are scoped to the caller's tenant and workspace; the caller
cannot widen that scope through arguments."""


def response_to_tool_payload(response: SearchResponse) -> dict[str, Any]:
    """Serialise a `SearchResponse` for the wire, preserving the §10 field names."""
    return {
        # Second of the two copies required by ADR-0028. Built fresh with every
        # response, so it is the one that is never stale.
        "contract": TOOL_CONTRACT_VERSION,
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
                # The id a policy rule names (ADR-0033), namespaced so it is
                # unique within the tenant the decision is evaluated in.
                "resource_id": doc.provenance.resource_id,
                "provenance": {
                    "document_id": doc.provenance.document_id,
                    "chunk_id": doc.provenance.chunk_id,
                    "workspace_id": doc.provenance.workspace_id,
                    "resource_id": doc.provenance.resource_id,
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

    Register it with `TOOL_DESCRIPTION`, whose first line carries the contract
    integer (ADR-0028). Do not hand-write a description here: the two copies of
    that integer have to move together or the diagnostic is worse than useless.

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
