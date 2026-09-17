"""Command line entry point (`enterprise-knowledge`).

Mirrors the dual-mode flags from the original specification, with retrieval and
generation kept separable (§13):

    enterprise-knowledge --mode direct --query "..." --tenant acme
    enterprise-knowledge --mode mcp --transport stdio
    enterprise-knowledge --reindex

§12: in `--mode mcp --transport stdio`, this process must not write anything to
stdout that is not JSON-RPC. `configure_logging()` is called before any other
work for exactly that reason.
"""

from __future__ import annotations

import argparse
import sys

from .config import configure_logging, load_settings

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="enterprise-knowledge")
    parser.add_argument("--mode", choices=("direct", "mcp"), default="direct")
    parser.add_argument("--transport", choices=("stdio", "sse"), default="stdio")
    parser.add_argument("--query")
    parser.add_argument("--tenant", help="tenant_id; required for any search (§4.3)")
    parser.add_argument("--workspace", help="workspace_id; required for knowledge (ADR-0007)")
    parser.add_argument("--principal", default="cli")
    # A label on a workspace (ADR-0007), so it filters metadata -- it does not
    # select a scope. Use --workspace for that.
    parser.add_argument("--dept", help="metadata label filter: department")
    parser.add_argument("--doc-type", help="metadata filter: document_type")
    parser.add_argument("--top-k", type=int)
    parser.add_argument(
        "--strategy",
        choices=("dense", "hybrid", "hybrid_rerank"),
        default="hybrid_rerank",
        help="benchmark arm to run (§16)",
    )
    parser.add_argument("--reindex", action="store_true", help="apply schema.sql and re-ingest")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    configure_logging(settings)

    print(
        "enterprise-knowledge: contract skeleton only -- "
        f"mode={args.mode} is wired in Phase 5 (see docs/architecture.md)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
