"""MCP conformance over the real protocol (§12, §19).

§19 is explicit: calling the Python function directly is not an MCP test. These
drive a spawned server over stdio, and the stdout-integrity assertion is the
reason the suite exists -- a stray `print()` corrupts JSON-RPC in a way no unit
test would catch.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.mcp


@pytest.mark.xfail(reason="Phase 5: build_mcp_server is not implemented yet")
def test_session_initializes_and_lists_the_knowledge_tool() -> None:
    """initialize -> list tools -> `search_company_knowledge` is present."""
    raise NotImplementedError


@pytest.mark.xfail(reason="Phase 5: tool call over a live stdio session")
def test_tool_call_returns_contract_shaped_payload() -> None:
    """Response carries documents/score/provenance/citation per §10."""
    raise NotImplementedError


@pytest.mark.xfail(reason="Phase 5: stdout must carry JSON-RPC frames only (§12)")
def test_stdout_contains_only_jsonrpc_frames() -> None:
    """Every stdout line must parse as JSON-RPC; logs belong on stderr."""
    raise NotImplementedError


@pytest.mark.xfail(reason="Phase 8: identity comes from session context, not tool args")
def test_tool_arguments_cannot_set_tenant_id() -> None:
    raise NotImplementedError
