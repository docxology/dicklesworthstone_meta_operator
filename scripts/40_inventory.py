#!/usr/bin/env python3
"""Build per-repo interpretability profiles into the corpus inventory.

Walks every clone (languages, LOC, manifests, entry points, test setup,
README digests, last commit) and writes ``output/data/inventory.json``:

    uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/40_inventory.py

Exits 1 when registry repos have no local clone yet (finish 20 first).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config  # noqa: E402
from src.inventory import build_inventory  # noqa: E402
from src.jsonio import write_json  # noqa: E402
from src.project_paths import INVENTORY, data_dir  # noqa: E402
from src.registry import load_registry, registry_names  # noqa: E402


def main() -> int:
    """Profile every clone; exit 1 when clones are missing."""
    config = load_config(REPO_ROOT)
    registry = load_registry(REPO_ROOT)
    names = registry_names(registry)
    if not names:
        print("registry is empty — run scripts/10_build_registry.py first")
        return 1
    inventory = build_inventory(names, REPO_ROOT / config.repos_dir)
    path = write_json(data_dir(REPO_ROOT) / INVENTORY, inventory)

    repos = inventory["repos"]
    missing = inventory["missing"]
    total_loc = sum(int(r.get("total_loc") or 0) for r in repos)
    with_tests = sum(1 for r in repos if r.get("has_tests"))
    print(f"inventory written: {path}")
    print(f"profiled: {len(repos)} repos, {total_loc} LOC, {with_tests} with tests")
    if missing:
        print(f"missing clones ({len(missing)}): {', '.join(missing[:10])}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
