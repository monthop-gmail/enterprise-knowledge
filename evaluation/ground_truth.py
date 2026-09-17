"""Ground-truth QA pairs (§15).

A benchmark without ground truth is forbidden (§25), so this module defines the
fixture corpus and the labelled cases before any measurement code exists.

Each case carries a metadata scope as well as expected documents: retrieval that
returns the right answer from the *wrong* scope is a security failure, not a
partial success (§26), and `expected_denied` cases exist to prove it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from enterprise_knowledge.contracts import CrossWorkspaceGrant

__all__ = [
    "FixtureDocument",
    "GroundTruthCase",
    "FIXTURE_CORPUS",
    "GROUND_TRUTH",
    "corpus_for",
    "workspace_corpus_for",
]


@dataclass(frozen=True, slots=True)
class FixtureDocument:
    document_id: str
    tenant_id: str
    workspace_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str | None = None


@dataclass(frozen=True, slots=True)
class GroundTruthCase:
    """One labelled query.

    `expected_document_ids` -- documents that *should* be retrieved.
    `expected_denied_document_ids` -- documents the scope must never surface;
    any appearance counts as scope leakage regardless of rank.

    `cross_workspace_grant` carries the policy decision that widens the search
    past its home workspace (ADR-0021). A case that sets it is asserting two
    things at once: the wider documents become reachable, *and* the crossing is
    attributable to a named decision.
    """

    case_id: str
    query: str
    tenant_id: str
    workspace_id: str
    expected_document_ids: tuple[str, ...]
    filters: dict[str, Any] = field(default_factory=dict)
    allowed_metadata: dict[str, list[str]] = field(default_factory=dict)
    expected_denied_document_ids: tuple[str, ...] = ()
    cross_workspace_grant: CrossWorkspaceGrant | None = None


# --- fixture corpus ---------------------------------------------------------
# Deliberately small and hand-written: an offline regression suite must be
# reviewable in a diff. Two tenants share vocabulary on purpose so a broken
# tenant filter shows up as a leak rather than as a miss, and `acme` spans two
# workspaces so the workspace scope has something real to exclude.
#
# `department` stays in metadata as a *label* (ADR-0007). The partition it used
# to stand in for is now `workspace_id`.

FIXTURE_CORPUS: tuple[FixtureDocument, ...] = (
    FixtureDocument(
        document_id="acme-hr-leave",
        tenant_id="acme",
        workspace_id="hr",
        content="Full-time staff accrue 10 days of annual leave per year. "
        "Unused leave expires 31 March of the following year.",
        metadata={"department": "hr", "document_type": "policy", "classification": "internal"},
        source="odoo://hr/leave-policy",
    ),
    FixtureDocument(
        document_id="acme-hr-remote",
        tenant_id="acme",
        workspace_id="hr",
        content="Remote work is approved for up to three days per week with manager sign-off.",
        metadata={"department": "hr", "document_type": "policy", "classification": "internal"},
        source="odoo://hr/remote-policy",
    ),
    FixtureDocument(
        document_id="acme-fin-expense",
        tenant_id="acme",
        workspace_id="finance",
        content="Expense claims above 5,000 THB require a receipt and director approval.",
        metadata={"department": "finance", "document_type": "policy", "classification": "internal"},
        source="odoo://finance/expense-policy",
    ),
    FixtureDocument(
        document_id="acme-sec-restricted",
        tenant_id="acme",
        workspace_id="hr",
        content="Board compensation review notes for the annual leave of the CEO.",
        metadata={"department": "hr", "document_type": "minutes", "classification": "restricted"},
        source="odoo://board/minutes-2026-03",
    ),
    FixtureDocument(
        document_id="globex-hr-leave",
        tenant_id="globex",
        workspace_id="hr",
        content="Employees accrue 15 days of annual leave per year under the Globex handbook.",
        metadata={"department": "hr", "document_type": "policy", "classification": "internal"},
        source="odoo://globex/hr/leave-policy",
    ),
)

GROUND_TRUTH: tuple[GroundTruthCase, ...] = (
    GroundTruthCase(
        case_id="leave-days",
        query="how many days of annual leave do staff get",
        tenant_id="acme",
        workspace_id="hr",
        expected_document_ids=("acme-hr-leave",),
        allowed_metadata={"classification": ["public", "internal"]},
        # Same tenant, same department, same vocabulary -- but restricted.
        expected_denied_document_ids=("acme-sec-restricted", "globex-hr-leave"),
    ),
    GroundTruthCase(
        case_id="remote-policy-hr-scope",
        query="can I work from home",
        tenant_id="acme",
        # The `hr` scope now comes from the workspace, not from a metadata
        # filter. `department` stays below as a label to prove both still work
        # and that the label alone is no longer what keeps finance out.
        workspace_id="hr",
        expected_document_ids=("acme-hr-remote",),
        filters={"department": "hr"},
        allowed_metadata={"classification": ["public", "internal"]},
        expected_denied_document_ids=("acme-fin-expense",),
    ),
    GroundTruthCase(
        case_id="expense-threshold",
        query="expense claim approval threshold receipt",
        tenant_id="acme",
        workspace_id="finance",
        expected_document_ids=("acme-fin-expense",),
        allowed_metadata={"classification": ["public", "internal"]},
        # Same tenant, different workspace: denied without a grant.
        expected_denied_document_ids=("globex-hr-leave", "acme-hr-leave", "acme-hr-remote"),
    ),
    GroundTruthCase(
        case_id="cross-tenant-isolation",
        query="annual leave handbook",
        tenant_id="globex",
        workspace_id="hr",
        expected_document_ids=("globex-hr-leave",),
        allowed_metadata={"classification": ["public", "internal"]},
        # The acme corpus must be invisible from globex, full stop (§4.3).
        expected_denied_document_ids=(
            "acme-hr-leave",
            "acme-hr-remote",
            "acme-fin-expense",
            "acme-sec-restricted",
        ),
    ),
    GroundTruthCase(
        case_id="workspace-denied-by-default",
        query="expense claim approval threshold receipt",
        tenant_id="acme",
        workspace_id="hr",
        # Nothing in `hr` answers this. The finance document does, and it is the
        # same tenant -- but no grant was issued, so it stays out of reach.
        expected_document_ids=(),
        allowed_metadata={"classification": ["public", "internal"]},
        expected_denied_document_ids=("acme-fin-expense",),
    ),
    GroundTruthCase(
        case_id="workspace-crossed-by-decision",
        query="expense claim approval threshold receipt",
        tenant_id="acme",
        workspace_id="hr",
        # Same query, same principal, same home workspace as the case above --
        # the only difference is the decision. If this case and the one above
        # return the same documents, the workspace scope is not doing anything.
        expected_document_ids=("acme-fin-expense",),
        allowed_metadata={"classification": ["public", "internal"]},
        cross_workspace_grant=CrossWorkspaceGrant(
            policy_decision_id="dec-hr-reads-finance-2026-09",
            workspace_ids=frozenset({"finance"}),
        ),
        # Widening reaches another workspace, never another tenant.
        expected_denied_document_ids=("globex-hr-leave",),
    ),
    GroundTruthCase(
        case_id="tenant-boundary-survives-a-grant",
        query="annual leave handbook",
        tenant_id="acme",
        workspace_id="hr",
        expected_document_ids=("acme-hr-leave",),
        allowed_metadata={"classification": ["public", "internal"]},
        # A grant naming globex's workspace is issued anyway. It must buy
        # nothing: no decision crosses a tenant (ADR-0021). The grant is valid
        # and still powerless, which is the point being proved.
        cross_workspace_grant=CrossWorkspaceGrant(
            policy_decision_id="dec-overbroad-grant-2026-09",
            workspace_ids=frozenset({"hr", "finance"}),
        ),
        expected_denied_document_ids=("globex-hr-leave", "acme-sec-restricted"),
    ),
)


def workspace_corpus_for(tenant_id: str, workspace_id: str) -> tuple[FixtureDocument, ...]:
    """Documents a search scoped to exactly this workspace may reach."""
    return tuple(
        d for d in FIXTURE_CORPUS if d.tenant_id == tenant_id and d.workspace_id == workspace_id
    )


def corpus_for(tenant_id: str) -> tuple[FixtureDocument, ...]:
    return tuple(d for d in FIXTURE_CORPUS if d.tenant_id == tenant_id)
