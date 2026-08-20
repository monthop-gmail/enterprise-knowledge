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


def test_contracts_module_has_no_third_party_imports() -> None:
    """The shared vocabulary must stay installable without a driver or SDK."""
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
