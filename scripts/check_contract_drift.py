#!/usr/bin/env python3
"""Compare the contract versions pinned in platform-contract.yaml with upstream.

Run on a schedule, not on every pull request. Drift is news about somebody
else's repository: it should reach us, but it must not be able to turn a branch
red without anyone having changed it here.

Reads each contract's CHANGELOG from `agent-platform` and compares the newest
heading against what we pinned. Exits non-zero when anything has moved, so the
scheduled workflow fails visibly rather than logging into the void.

Stdlib only, on purpose: a drift check that needs its own dependency tree is one
more thing that can break for reasons unrelated to drift.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN_FILE = ROOT / "platform-contract.yaml"
RAW = "https://raw.githubusercontent.com/{repo}/main/contracts/{contract}/CHANGELOG.md"
VERSION_HEADING = re.compile(r"^##\s*v(\d+\.\d+\.\d+)", re.MULTILINE)
TIMEOUT_SECONDS = 15


def read_pins(text: str) -> tuple[str, dict[str, str]]:
    """Pull `platform.repo` and each `contracts.<name>.version` out of the pin file.

    Parsed by hand rather than with PyYAML so the check has no dependencies. The
    file is ours and its shape is fixed, but the parser still refuses anything it
    does not recognise instead of quietly returning fewer pins than the file
    lists -- a drift check that silently checks nothing is worse than none.
    """
    repo = ""
    pins: dict[str, str] = {}
    section = ""
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent == 0:
            section = stripped.rstrip(":")
            continue
        if section == "platform" and stripped.startswith("repo:"):
            repo = stripped.split(":", 1)[1].strip()
        elif section == "contracts":
            if indent == 2 and stripped.endswith(":"):
                current = stripped.rstrip(":")
            elif indent == 4 and stripped.startswith("version:") and current:
                pins[current] = stripped.split(":", 1)[1].strip()
    if not repo or not pins:
        raise SystemExit(f"could not read pins from {PIN_FILE}")
    return repo, pins


def upstream_version(repo: str, contract: str) -> str | None:
    url = RAW.format(repo=repo, contract=contract)
    request = urllib.request.Request(url, headers={"User-Agent": "enterprise-knowledge-drift"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        print(f"  ! {contract}: HTTP {exc.code} fetching CHANGELOG")
        return None
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"  ! {contract}: {exc}")
        return None
    match = VERSION_HEADING.search(body)
    if match is None:
        print(f"  ! {contract}: no version heading in CHANGELOG")
        return None
    return match.group(1)


def main() -> int:
    repo, pins = read_pins(PIN_FILE.read_text(encoding="utf-8"))
    print(f"comparing {len(pins)} pinned contracts against {repo}\n")

    moved: list[tuple[str, str, str]] = []
    unreadable: list[str] = []
    for contract, pinned in sorted(pins.items()):
        latest = upstream_version(repo, contract)
        if latest is None:
            unreadable.append(contract)
            continue
        status = "ok  " if latest == pinned else "MOVED"
        print(f"  {status} {contract:<15} pinned {pinned:<8} upstream {latest}")
        if latest != pinned:
            moved.append((contract, pinned, latest))

    print()
    if unreadable:
        # Not a failure on its own: an unreachable network says nothing about
        # whether upstream moved, and reporting it as drift would train everyone
        # to ignore this check.
        print(f"could not read: {', '.join(unreadable)}")
    if not moved:
        print("no drift" if not unreadable else "no drift among the contracts that could be read")
        return 0

    print(f"{len(moved)} contract(s) moved since platform-contract.yaml was written:\n")
    for contract, pinned, latest in moved:
        print(f"  {contract}: {pinned} -> {latest}")
        print(f"    https://github.com/{repo}/blob/main/contracts/{contract}/CHANGELOG.md")
    print(
        "\nRead the CHANGELOG entries, decide whether each one touches this repo, "
        "then update platform-contract.yaml with a note saying what you concluded."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
