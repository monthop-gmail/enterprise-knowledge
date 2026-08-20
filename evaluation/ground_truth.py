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

__all__ = ["FixtureDocument", "GroundTruthCase", "FIXTURE_CORPUS", "GROUND_TRUTH", "corpus_for"]


@dataclass(frozen=True, slots=True)
class FixtureDocument:
    document_id: str
    tenant_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str | None = None


@dataclass(frozen=True, slots=True)
class GroundTruthCase:
    """One labelled query.

    `expected_document_ids` -- documents that *should* be retrieved.
    `expected_denied_document_ids` -- documents the scope must never surface;
    any appearance counts as metadata/tenant leakage regardless of rank.
    """

    case_id: str
    query: str
    tenant_id: str
    expected_document_ids: tuple[str, ...]
    filters: dict[str, Any] = field(default_factory=dict)
    allowed_metadata: dict[str, list[str]] = field(default_factory=dict)
    expected_denied_document_ids: tuple[str, ...] = ()


# --- fixture corpus ---------------------------------------------------------
# Deliberately small and hand-written: an offline regression suite must be
# reviewable in a diff. Two tenants share vocabulary on purpose so a broken
# tenant filter shows up as a leak rather than as a miss.

FIXTURE_CORPUS: tuple[FixtureDocument, ...] = (
    FixtureDocument(
        document_id="acme-hr-leave",
        tenant_id="acme",
        content="Full-time staff accrue 10 days of annual leave per year. "
        "Unused leave expires 31 March of the following year.",
        metadata={"department": "hr", "document_type": "policy", "classification": "internal"},
        source="odoo://hr/leave-policy",
    ),
    FixtureDocument(
        document_id="acme-hr-remote",
        tenant_id="acme",
        content="Remote work is approved for up to three days per week with manager sign-off.",
        metadata={"department": "hr", "document_type": "policy", "classification": "internal"},
        source="odoo://hr/remote-policy",
    ),
    FixtureDocument(
        document_id="acme-fin-expense",
        tenant_id="acme",
        content="Expense claims above 5,000 THB require a receipt and director approval.",
        metadata={"department": "finance", "document_type": "policy", "classification": "internal"},
        source="odoo://finance/expense-policy",
    ),
    FixtureDocument(
        document_id="acme-sec-restricted",
        tenant_id="acme",
        content="Board compensation review notes for the annual leave of the CEO.",
        metadata={"department": "hr", "document_type": "minutes", "classification": "restricted"},
        source="odoo://board/minutes-2026-03",
    ),
    FixtureDocument(
        document_id="globex-hr-leave",
        tenant_id="globex",
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
        expected_document_ids=("acme-hr-leave",),
        allowed_metadata={"classification": ["public", "internal"]},
        # Same tenant, same department, same vocabulary -- but restricted.
        expected_denied_document_ids=("acme-sec-restricted", "globex-hr-leave"),
    ),
    GroundTruthCase(
        case_id="remote-policy-hr-scope",
        query="can I work from home",
        tenant_id="acme",
        expected_document_ids=("acme-hr-remote",),
        filters={"department": "hr"},
        allowed_metadata={"classification": ["public", "internal"]},
        expected_denied_document_ids=("acme-fin-expense",),
    ),
    GroundTruthCase(
        case_id="expense-threshold",
        query="expense claim approval threshold receipt",
        tenant_id="acme",
        expected_document_ids=("acme-fin-expense",),
        allowed_metadata={"classification": ["public", "internal"]},
        expected_denied_document_ids=("globex-hr-leave",),
    ),
    GroundTruthCase(
        case_id="cross-tenant-isolation",
        query="annual leave handbook",
        tenant_id="globex",
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
)


def corpus_for(tenant_id: str) -> tuple[FixtureDocument, ...]:
    return tuple(d for d in FIXTURE_CORPUS if d.tenant_id == tenant_id)
