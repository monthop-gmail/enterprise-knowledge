"""The ACL pre-filter is the security boundary (§4.2, §4.3)."""

from __future__ import annotations

import pytest

from enterprise_knowledge.contracts import Principal
from enterprise_knowledge.errors import PolicyViolation, TenantBoundaryViolation
from enterprise_knowledge.security import build_scope_predicate, resolve_policy


def test_tenant_is_always_present(policy) -> None:
    scope = build_scope_predicate(policy)
    assert scope.sql.startswith("tenant_id = %s")
    assert scope.params[0] == "acme"


def test_tenant_cannot_be_empty() -> None:
    with pytest.raises(ValueError):
        resolve_policy("", Principal("u-1"))


def test_caller_cannot_override_tenant(policy) -> None:
    with pytest.raises(TenantBoundaryViolation):
        build_scope_predicate(policy, {"tenant_id": "globex"})


def test_empty_allow_list_is_rejected_not_ignored() -> None:
    policy = resolve_policy("acme", Principal("u-1"), {"classification": []})
    with pytest.raises(PolicyViolation):
        build_scope_predicate(policy)


def test_filters_narrow_and_are_parameterised(policy) -> None:
    scope = build_scope_predicate(policy, {"department": "hr"})
    assert "metadata @> %s::jsonb" in scope.sql
    assert '{"department": "hr"}' in scope.params
    # No caller value is ever spliced into SQL text.
    assert "hr" not in scope.sql


def test_acl_key_uses_bound_values(policy) -> None:
    scope = build_scope_predicate(policy)
    assert "metadata ->> %s = ANY(%s)" in scope.sql
    assert "classification" in scope.params
    assert ["public", "internal"] in scope.params


def test_predicate_count_grows_with_policy(policy) -> None:
    bare = build_scope_predicate(resolve_policy("acme", Principal("u-1")))
    full = build_scope_predicate(policy, {"department": "hr"})
    assert len(bare.params) == 1
    assert len(full.params) == 4
