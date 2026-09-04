#!/usr/bin/env python3
"""Generate the four manuscript figures from the built artifacts.

Reads the registry, upstream status, and inventory JSON artifacts, then writes
the PNGs into ``output/figures/``:

    python scripts/65_generate_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src import jsonio, project_paths  # noqa: E402
from src.figures import build_all_figures  # noqa: E402


def main() -> int:
    """Render all figures; exit 1 when a required upstream artifact is missing."""
    ddir = project_paths.data_dir(REPO_ROOT)
    try:
        registry = jsonio.read_json(ddir / project_paths.REPO_REGISTRY)
        upstream = jsonio.read_json(ddir / project_paths.UPSTREAM_STATUS)
        inventory = jsonio.read_json(ddir / project_paths.INVENTORY)
    except FileNotFoundError as exc:
        sys.stderr.write(f"{exc}\nfix: run scripts/30_verify_upstream.py and scripts/40_inventory.py first\n")
        return 1
    written = build_all_figures(registry, upstream, inventory, project_paths.figures_dir(REPO_ROOT))
    for path in written:
        print(f"figure written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
