"""The ACL pre-filter is the security boundary (§4.2, §4.3)."""

from __future__ import annotations

import pytest

from enterprise_knowledge.contracts import CrossWorkspaceGrant, Principal
from enterprise_knowledge.errors import PolicyViolation, TenantBoundaryViolation
from enterprise_knowledge.security import build_scope_predicate, resolve_policy


def test_tenant_is_always_present(policy) -> None:
    scope = build_scope_predicate(policy)
    assert scope.sql.startswith("tenant_id = %s")
    assert scope.params[0] == "acme"


def test_tenant_cannot_be_empty() -> None:
    with pytest.raises(ValueError):
        resolve_policy("", "hr", Principal("u-1"))


def test_workspace_cannot_be_empty() -> None:
    """ADR-0007: workspace_id is required for knowledge, optional only for events."""
    with pytest.raises(ValueError):
        resolve_policy("acme", "", Principal("u-1"))


def test_workspace_is_scoped_to_home_by_default(policy) -> None:
    scope = build_scope_predicate(policy)
    assert "workspace_id = ANY(%s)" in scope.sql
    assert ["hr"] in scope.params, "deny by default: only the home workspace"


def test_grant_widens_the_workspace_list_and_nothing_else(policy) -> None:
    granted = resolve_policy(
        "acme",
        "hr",
        policy.principal,
        policy.allowed_metadata,
        CrossWorkspaceGrant("dec-1", frozenset({"finance"})),
    )
    narrow = build_scope_predicate(policy)
    wide = build_scope_predicate(granted)

    # Same statement either way -- widening is data, not a second code path.
    assert narrow.sql == wide.sql
    assert ["finance", "hr"] in wide.params
    # The tenant bind is untouched by any grant.
    assert narrow.params[0] == wide.params[0] == "acme"


def test_a_grant_cannot_reach_another_tenant(policy) -> None:
    """ADR-0021: no decision crosses a tenant, however the grant is worded."""
    granted = resolve_policy(
        "acme",
        "hr",
        policy.principal,
        policy.allowed_metadata,
        CrossWorkspaceGrant("dec-overbroad", frozenset({"hr", "finance"})),
    )
    scope = build_scope_predicate(granted)
    assert scope.sql.startswith("tenant_id = %s")
    assert scope.params[0] == "acme"


def test_grant_without_a_decision_id_cannot_be_built() -> None:
    """A silent crossing is indistinguishable from having no workspace at all."""
    with pytest.raises(ValueError, match="policy decision"):
        CrossWorkspaceGrant("", frozenset({"finance"}))


def test_grant_that_widens_to_nothing_is_rejected() -> None:
    with pytest.raises(ValueError):
        CrossWorkspaceGrant("dec-1", frozenset())


def test_caller_cannot_name_its_own_workspace(policy) -> None:
    from enterprise_knowledge.errors import TenantBoundaryViolation

    with pytest.raises(TenantBoundaryViolation):
        build_scope_predicate(policy, {"workspace_id": "finance"})


def test_caller_cannot_override_tenant(policy) -> None:
    with pytest.raises(TenantBoundaryViolation):
        build_scope_predicate(policy, {"tenant_id": "globex"})


def test_empty_allow_list_is_rejected_not_ignored() -> None:
    policy = resolve_policy("acme", "hr", Principal("u-1"), {"classification": []})
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
    bare = build_scope_predicate(resolve_policy("acme", "hr", Principal("u-1")))
    full = build_scope_predicate(policy, {"department": "hr"})
    assert len(bare.params) == 2  # tenant + workspace
    assert len(full.params) == 5  # + acl key, acl values, filters


def test_department_is_a_label_not_a_scope(policy) -> None:
    """ADR-0007: department filters metadata; the partition is the workspace."""
    scope = build_scope_predicate(policy, {"department": "hr"})
    assert "metadata @> %s::jsonb" in scope.sql
    assert '{"department": "hr"}' in scope.params
    # It is not, and must never become, a column predicate.
    assert "department =" not in scope.sql
