"""Stage-1 SQL shape: the security property must survive Phase 2 (§4.2, §5, §9)."""

from __future__ import annotations

import pytest

from enterprise_knowledge.config import RetrievalConfig
from enterprise_knowledge.contracts import Principal
from enterprise_knowledge.retrieval import build_stage1_params, build_stage1_sql
from enterprise_knowledge.security import build_scope_predicate, resolve_policy

SCOPES = [
    ({}, None),
    ({"classification": ["public", "internal"]}, {"department": "hr"}),
    ({"classification": ["public"], "region": ["apac"]}, {"document_type": "policy"}),
]


@pytest.mark.parametrize("allowed,filters", SCOPES)
def test_bind_arity_matches_placeholders(allowed, filters) -> None:
    scope = build_scope_predicate(resolve_policy("acme", Principal("u-1"), allowed), filters)
    sql = build_stage1_sql(scope)
    params = build_stage1_params(scope, "q", [0.1, 0.2], RetrievalConfig())
    assert sql.count("%s") == len(params)


def test_scope_is_inside_both_ctes_not_applied_after() -> None:
    scope = build_scope_predicate(resolve_policy("acme", Principal("u-1")))
    sql = build_stage1_sql(scope)
    dense_cte = sql.split("sparse AS (")[0]
    sparse_cte = sql.split("sparse AS (")[1].split("fused AS (")[0]
    assert scope.sql in dense_cte, "dense CTE must carry the ACL pre-filter"
    assert scope.sql in sparse_cte, "sparse CTE must carry the ACL pre-filter"
    # The fused CTE reads only from the two pre-filtered CTEs.
    assert "FROM langchain_hybrid_docs" not in sql.split("fused AS (")[1]


def test_uses_cosine_distance_and_ts_rank_cd() -> None:
    scope = build_scope_predicate(resolve_policy("acme", Principal("u-1")))
    sql = build_stage1_sql(scope)
    assert "<=>" in sql, "§5 specifies cosine distance"
    assert "ts_rank_cd(" in sql, "§5 specifies ts_rank_cd for sparse ranking"


def test_rrf_denominator_is_configurable_in_sql() -> None:
    scope = build_scope_predicate(resolve_policy("acme", Principal("u-1")))
    sql = build_stage1_sql(scope)
    assert "1.0 / (%s + d.rank)" in sql
    assert "1.0 / (%s + s.rank)" in sql
    assert "1.0 / (60" not in sql, "rrf_k must be bound, not hard-coded"
