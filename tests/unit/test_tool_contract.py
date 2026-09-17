"""Tool-response contract rules (ADR-0027, ADR-0028)."""

from __future__ import annotations

from enterprise_knowledge.contracts import RetrievalStrategy, SearchResponse, Timings
from enterprise_knowledge.mcp import (
    TOOL_CONTRACT_VERSION,
    TOOL_DESCRIPTION,
    TOOL_NAME,
    response_to_tool_payload,
)
from enterprise_knowledge.provenance import to_retrieved_chunk
from enterprise_knowledge.retrieval import Candidate


def payload() -> dict[str, object]:
    doc = to_retrieved_chunk(Candidate("c1", "body", {}, "doc-1", "hr"), score=1.0)
    return response_to_tool_payload(
        SearchResponse("q", [doc], Timings(), RetrievalStrategy.HYBRID, "acme")
    )


def test_the_contract_number_appears_in_both_cached_places() -> None:
    """ADR-0028: one copy in the tool description (stale on the client) and one
    in every freshly built result (never stale). A caller comparing them can
    tell it is holding an old description instead of guessing."""
    first_line = TOOL_DESCRIPTION.splitlines()[0]
    assert first_line == f"contract {TOOL_CONTRACT_VERSION}"
    assert payload()["contract"] == TOOL_CONTRACT_VERSION


def test_tool_name_survives_the_toolid_transformation_unchanged() -> None:
    """ADR-0027: lowercase, then every character outside [a-z0-9_] becomes `_`
    one for one. A name that is already canonical cannot be renamed by a
    connector on the way through, so the ceiling written about it still binds."""
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_"
    transformed = "".join(c if c in allowed else "_" for c in TOOL_NAME.lower())
    assert transformed == TOOL_NAME


def test_response_keys_are_additive_only() -> None:
    """ADR-0028 forbids removing or renaming a key within a major version.

    This list is the published surface. Removing an entry here is the change the
    rule prohibits, so the test is meant to fail loudly and be argued with --
    not updated to match whatever the code now returns.
    """
    published = {"contract", "query", "tenant_id", "strategy", "documents", "timings_ms"}
    assert published <= payload().keys()

    document_keys = {
        "content",
        "score",
        "metadata",
        "document_id",
        "chunk_id",
        "resource_id",
        "source",
        "provenance",
        "citation",
    }
    assert document_keys <= payload()["documents"][0].keys()  # type: ignore[index]
