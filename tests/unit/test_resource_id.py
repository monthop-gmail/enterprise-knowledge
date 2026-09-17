"""`policy/v1.action.resource` must be tenant-unique (ADR-0033).

The rule is enforceable only at the producer -- the central validator can check
nothing beyond "it is a string" (`platform_rules` item 7). These tests are that
enforcement.
"""

from __future__ import annotations

import pytest

from enterprise_knowledge.mcp import response_to_tool_payload
from enterprise_knowledge.provenance import (
    RESOURCE_NAMESPACE_SEPARATOR,
    build_resource_id,
    parse_resource_id,
    to_retrieved_chunk,
)
from enterprise_knowledge.retrieval import Candidate


def chunk(document_id: str = "doc-1", workspace_id: str = "hr") -> Candidate:
    return Candidate("c1", "body", {}, document_id, workspace_id)


def test_the_namespace_is_the_workspace() -> None:
    """A document id here is unique per (tenant, workspace, document), so the
    workspace is what lifts it to tenant-unique."""
    assert build_resource_id("hr", "acme-hr-leave") == "hr:acme-hr-leave"


def test_the_prefix_is_reversible() -> None:
    """ADR-0033 requires the namespacing to be undoable, so it is tested rather
    than asserted in prose."""
    for workspace_id, document_id in [
        ("hr", "acme-hr-leave"),
        ("finance", "a-b-c"),
        ("ws_1", "doc_with_underscores"),
    ]:
        assert parse_resource_id(build_resource_id(workspace_id, document_id)) == (
            workspace_id,
            document_id,
        )


def test_the_separator_cannot_occur_inside_an_id() -> None:
    """Reversibility holds only because `identity/v1#/$defs/Id` is `[a-z0-9_-]`.

    A workspace carrying the separator would make the split ambiguous, so it is
    refused rather than silently producing an id that parses back wrong.
    """
    with pytest.raises(ValueError, match="reversible"):
        build_resource_id(f"hr{RESOURCE_NAMESPACE_SEPARATOR}x", "doc-1")


def test_documents_in_different_workspaces_do_not_collide() -> None:
    """The whole point: the same document id in two workspaces is two resources."""
    assert build_resource_id("hr", "policy") != build_resource_id("finance", "policy")


def test_an_incomplete_resource_id_is_refused() -> None:
    for bad in ("", "hr", ":doc", "hr:"):
        with pytest.raises(ValueError):
            parse_resource_id(bad)


def test_every_result_carries_a_resource_id() -> None:
    result = to_retrieved_chunk(chunk(), score=1.0)
    assert result.provenance.resource_id == "hr:doc-1"
    assert result.provenance.workspace_id == "hr"


def test_the_tool_payload_exposes_it() -> None:
    from enterprise_knowledge.contracts import RetrievalStrategy, SearchResponse, Timings

    doc = to_retrieved_chunk(chunk(), score=1.0)
    payload = response_to_tool_payload(
        SearchResponse("q", [doc], Timings(), RetrievalStrategy.HYBRID, "acme")
    )
    assert payload["documents"][0]["resource_id"] == "hr:doc-1"
    assert payload["documents"][0]["provenance"]["resource_id"] == "hr:doc-1"
