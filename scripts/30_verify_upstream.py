#!/usr/bin/env python3
"""Verify every clone is on its upstream default branch, clean worktree.

Fetches ``origin`` per clone (parallel), compares HEAD with
``origin/<default_branch>``, classifies each repo into a state, and writes
``output/data/upstream_status.json``:

    uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/30_verify_upstream.py

Exits 1 when any repo is not in an OK state (on_upstream / unborn).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config  # noqa: E402
from src.jsonio import write_json  # noqa: E402
from src.models import UPSTREAM_OK_STATES  # noqa: E402
from src.project_paths import UPSTREAM_STATUS, data_dir  # noqa: E402
from src.registry import load_registry, registry_metas  # noqa: E402
from src.upstream_check import build_report, verify_all  # noqa: E402


def main() -> int:
    """Verify the whole corpus; exit 1 when any clone is off its upstream."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="verify against cached remote refs (no network; accurate right after a clone)",
    )
    parser.add_argument(
        "--full-fetch",
        action="store_true",
        help="fetch every repo instead of the default smart mode "
        "(offline pass first, fetch only repos not cleanly synced)",
    )
    args = parser.parse_args()
    config = load_config(REPO_ROOT)
    registry = load_registry(REPO_ROOT)
    metas = registry_metas(registry)
    if not metas:
        print("registry is empty — run scripts/10_build_registry.py first")
        return 1
    repos_dir = REPO_ROOT / config.repos_dir
    requests = [
        (name, repos_dir / name, meta.default_branch) for name, meta in metas.items()
    ]
    statuses = verify_all(
        requests,
        do_fetch=not args.no_fetch,
        fetch_workers=config.fetch_workers,
        smart_fetch=not args.full_fetch,
    )
    report = build_report(statuses)
    path = write_json(data_dir(REPO_ROOT) / UPSTREAM_STATUS, report)
    print(f"upstream status written: {path}")

    state_counts: dict[str, int] = {}
    for status in statuses:
        state_counts[status.state] = state_counts.get(status.state, 0) + 1
    for state, count in sorted(state_counts.items()):
        marker = "ok" if state in UPSTREAM_OK_STATES else "NOT OK"
        print(f"  {state}: {count} ({marker})")

    offenders = [s for s in statuses if s.state not in UPSTREAM_OK_STATES]
    for status in offenders[:20]:
        print(f"  {status.name}: {status.state}")
    if len(offenders) > 20:
        print(f"  ... and {len(offenders) - 20} more")
    return 0 if not offenders else 1


if __name__ == "__main__":
    sys.exit(main())
