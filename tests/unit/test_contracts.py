"""Contract invariants other repos are allowed to depend on (§10, §11)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from enterprise_knowledge.config import RetrievalConfig
from enterprise_knowledge.contracts import (
    RetrievalStrategy,
    SearchRequest,
    TenantScope,
)
from enterprise_knowledge.errors import ConfigurationError
from enterprise_knowledge.mcp import response_to_tool_payload
from enterprise_knowledge.provenance import to_retrieved_chunk
from enterprise_knowledge.retrieval import Candidate


def test_no_contract_identifier_is_named_subject() -> None:
    """ADR-0017 vocabulary lock: the caller is the `actor`, never the `subject`.

    In this domain the actor and the person a document is about are different
    people in exactly the cases that matter, and Python has no schema validator
    to catch the swap -- so the guard is the naming.

    Checks declared identifiers via the AST rather than raw text, so prose that
    explains the rule does not trip the rule.
    """
    import ast

    import enterprise_knowledge.contracts as contracts

    tree = ast.parse(Path(contracts.__file__).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef | ast.FunctionDef):
            names.append(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
        elif isinstance(node, ast.Name):
            names.append(node.id)
    offenders = [n for n in names if "subject" in n.lower()]
    assert not offenders, f"use 'actor' instead (ADR-0017): {offenders}"


def test_principal_carries_the_platform_required_fields() -> None:
    """`identity/v1#/$defs/Principal` requires `type` and `id`."""
    from enterprise_knowledge.contracts import Principal, PrincipalType

    agent = Principal("agent-1", type=PrincipalType.AGENT,
                      on_behalf_of=Principal("u-1", type=PrincipalType.HUMAN))
    assert agent.type is PrincipalType.AGENT
    assert agent.on_behalf_of is not None
    assert agent.on_behalf_of.type is PrincipalType.HUMAN


def test_contracts_module_has_no_third_party_imports() -> None:
    """The contract projection must stay importable without a driver or SDK.

    Not because `agent-platform` imports it -- that repo holds YAML and JSON
    Schema only (ADR-0008) and cannot import Python. The reason is local: every
    adapter and translation layer here has to reach these types, and none of them
    should inherit psycopg or an SDK to do it.
    """
    import enterprise_knowledge.contracts as contracts

    source = Path(contracts.__file__).read_text(encoding="utf-8")
    for banned in ("import psycopg", "import openai", "import pydantic", "import flashrank"):
        assert banned not in source


def test_request_defaults_to_the_full_two_stage_pipeline(policy) -> None:
    assert SearchRequest("q", policy).strategy is RetrievalStrategy.HYBRID_RERANK


def test_policy_context_is_immutable(policy) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.tenant = TenantScope("globex")  # type: ignore[misc]


def test_tenant_scope_has_no_wildcard() -> None:
    for value in ("", "   "):
        with pytest.raises(ValueError):
            TenantScope(value)


def test_workspace_scope_has_no_wildcard() -> None:
    from enterprise_knowledge.contracts import WorkspaceScope

    for value in ("", "   "):
        with pytest.raises(ValueError):
            WorkspaceScope(value)


def test_final_k_cannot_exceed_candidate_k() -> None:
    with pytest.raises(ConfigurationError):
        RetrievalConfig(candidate_k=5, final_k=10)


def test_every_result_carries_provenance_and_citation() -> None:
    chunk = to_retrieved_chunk(
        Candidate("c1", "body", {"title": "Handbook"}, "doc-1", 0, "odoo://hr/1"),
        score=0.42,
    )
    assert chunk.provenance.document_id == "doc-1"
    assert chunk.provenance.chunk_id == "c1"
    assert chunk.citation.label == "Handbook"
    assert chunk.citation.snippet


def test_mcp_payload_uses_contract_field_names(policy) -> None:
    from enterprise_knowledge.contracts import SearchResponse, Timings

    chunk = to_retrieved_chunk(Candidate("c1", "body", {}, "doc-1"), score=1.0)
    payload = response_to_tool_payload(
        SearchResponse("q", [chunk], Timings(), RetrievalStrategy.HYBRID, "acme")
    )
    doc = payload["documents"][0]
    # §11: the adapter translates the contract, it does not invent a new one.
    expected_keys = (
        "content", "score", "metadata", "document_id", "chunk_id", "provenance", "citation",
    )
    for key in expected_keys:
        assert key in doc
    assert set(payload["timings_ms"]) >= {"dense", "sparse", "rrf", "rerank", "retrieval_total"}
