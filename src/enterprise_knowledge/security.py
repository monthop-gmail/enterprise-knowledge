"""Tenant isolation, ACL scope, and policy context (§4.2, §4.3, §8 of the DoD).

The single rule this module exists to enforce:

    Identity -> Policy/ACL scope -> SQL pre-filter -> retrieval

never

    retrieval -> filter

Temporarily holding a row the principal may not see is already a violation
(§4.2), so the scope predicate produced here is injected *into* both retrieval
CTEs rather than applied to their output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .contracts import MetadataFilter, PolicyContext, Principal, TenantScope
from .errors import PolicyViolation, TenantBoundaryViolation

__all__ = [
    "ScopePredicate",
    "build_scope_predicate",
    "resolve_policy",
    "RESERVED_METADATA_KEYS",
]

# Keys a caller may never set through `filters`: they are boundary columns owned
# by the security layer, not searchable metadata.
RESERVED_METADATA_KEYS = frozenset({"tenant_id", "principal_id", "_acl"})


@dataclass(frozen=True, slots=True)
class ScopePredicate:
    """A parameterised SQL fragment plus its bind values.

    `sql` is spliced into the WHERE clause of every retrieval CTE. It never
    contains interpolated user input -- values travel in `params` so the driver
    binds them.
    """

    sql: str
    params: tuple[Any, ...]

    def and_(self, other: ScopePredicate) -> ScopePredicate:
        return ScopePredicate(f"({self.sql}) AND ({other.sql})", self.params + other.params)


def resolve_policy(
    tenant_id: str,
    principal: Principal,
    allowed_metadata: dict[str, list[str]] | None = None,
) -> PolicyContext:
    """Build the PolicyContext for one request.

    In production this is where `agent-platform`'s identity/policy plane is
    consulted (Phase 9). Until then it is a pure constructor that still refuses
    to build an unscoped context.
    """
    return PolicyContext(
        tenant=TenantScope(tenant_id),
        principal=principal,
        allowed_metadata=dict(allowed_metadata or {}),
    )


def build_scope_predicate(
    policy: PolicyContext,
    filters: MetadataFilter | None = None,
) -> ScopePredicate:
    """Compile policy + caller filters into one pre-filter predicate.

    Precedence, highest first:

    1. **Tenant** -- `tenant_id = %s`. Always present, never overridable.
    2. **ACL** -- for every key in `policy.allowed_metadata`, the row's metadata
       value must be in the allowed list. Deny-by-default: a document that does
       not carry a governed key is *not* visible, because an absent value cannot
       be shown to be permitted.
    3. **Caller filters** -- JSONB containment (`metadata @> %s::jsonb`), a
       preference that can only narrow, never widen.
    """
    filters = dict(filters or {})

    leaked = RESERVED_METADATA_KEYS & filters.keys()
    if leaked:
        raise TenantBoundaryViolation(
            f"filters may not contain security-owned keys: {sorted(leaked)}"
        )

    sql_parts = ["tenant_id = %s"]
    params: list[Any] = [policy.tenant.tenant_id]

    for key in sorted(policy.allowed_metadata):
        allowed = policy.allowed_metadata[key]
        if not allowed:
            raise PolicyViolation(
                f"allowed_metadata[{key!r}] is empty: an empty allow-list denies everything; "
                "omit the key instead if it should not be governed"
            )
        # `->>` yields NULL for a missing key, and `NULL = ANY(...)` is NULL,
        # which WHERE treats as false -- deny-by-default falls out for free.
        sql_parts.append("metadata ->> %s = ANY(%s)")
        params.extend([key, list(allowed)])

    if filters:
        sql_parts.append("metadata @> %s::jsonb")
        params.append(json.dumps(filters, sort_keys=True, ensure_ascii=False))

    return ScopePredicate(" AND ".join(sql_parts), tuple(params))
