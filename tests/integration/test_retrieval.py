"""End-to-end stage 1 + stage 2 against real data (§18, §19).

Phase 2/3 fills these in. They are written now so the acceptance criteria are
visible before the implementation exists.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.xfail(reason="Phase 2: SqlHybridRetriever.retrieve is not implemented yet")
def test_hybrid_beats_dense_on_the_fixture_corpus() -> None:
    raise NotImplementedError


@pytest.mark.xfail(reason="Phase 8: cross-tenant isolation under a live index")
def test_cross_tenant_query_returns_nothing_from_the_other_tenant() -> None:
    """The `cross-tenant-isolation` ground-truth case must report zero leakage."""
    raise NotImplementedError


@pytest.mark.xfail(reason="Phase 8: restricted classification must never surface")
def test_restricted_document_is_unreachable_for_an_internal_principal() -> None:
    raise NotImplementedError
