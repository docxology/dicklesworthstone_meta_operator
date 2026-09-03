#!/usr/bin/env python3
"""Render the static dashboard and corpus catalog from built artifacts.

Reads the registry, upstream status, inventory, and latest run, then writes
``output/web/dashboard.html`` (self-contained HTML, no network) and
``output/data/corpus_catalog.md``:

    uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/60_dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.dashboard import compute_summary, load_payload, write_artifacts  # noqa: E402


def main() -> int:
    """Render dashboard + catalog; exit 1 when the registry is missing."""
    try:
        payload = load_payload(REPO_ROOT)
    except RuntimeError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    summary = compute_summary(payload)
    dash_path, catalog_path = write_artifacts(payload, summary, REPO_ROOT)
    print(f"dashboard written: {dash_path}")
    print(f"catalog written: {catalog_path}")
    print(
        f"summary: {summary['total']} repos, {summary['upstream_ok']}/{summary['total']} "
        f"upstream-ok, {summary['total_loc']} LOC"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
