#!/usr/bin/env python3
"""Clone every registry repo into ``repos/`` (idempotent, parallel).

Already-cloned repos are detected (``.git`` present) and skipped, so this is
safe to re-run after an interrupted clone:

    uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/20_clone_corpus.py

Writes ``output/data/clone_outcomes.json``; exits 1 when any clone failed.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.cloner import clone_corpus  # noqa: E402
from src.config import load_config  # noqa: E402
from src.jsonio import write_json  # noqa: E402
from src.models import CLONE_FAILED_STATUSES, to_dict  # noqa: E402
from src.project_paths import data_dir  # noqa: E402
from src.registry import load_registry  # noqa: E402


def main() -> int:
    """Clone the corpus and persist outcomes; exit 1 on any failure."""
    config = load_config(REPO_ROOT)
    registry = load_registry(REPO_ROOT)
    outcomes = clone_corpus(registry, REPO_ROOT, workers=config.clone_workers)

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    failed = [o for o in outcomes if o.status in CLONE_FAILED_STATUSES]
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status_counts": dict(sorted(counts.items())),
        "failed": [to_dict(o) for o in failed],
        "repos": [to_dict(o) for o in outcomes],
    }
    path = write_json(data_dir(REPO_ROOT) / "clone_outcomes.json", payload)
    print(f"clone outcomes written: {path}")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    for outcome in failed:
        print(f"  FAILED {outcome.name}: {(outcome.error or '').strip()[:200]}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
