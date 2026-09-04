#!/usr/bin/env python3
"""Generate manuscript ``{{TOKEN}}`` variables from tracked artifacts.

Strict mode (default) requires all pipeline artifacts and the four figures;
draft mode (``--allow-draft``) emits "N/A" placeholders for early manuscript
drafts that may render without full evidence:

    uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/z_generate_manuscript_variables.py
    uv run python ... /scripts/z_generate_manuscript_variables.py --allow-draft
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.manuscript_variables import generate_variables, save_variables  # noqa: E402
from src.project_paths import data_dir  # noqa: E402


def main() -> int:
    """Hydrate the token map; exit 1 when strict requirements are unmet."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="emit N/A placeholders instead of failing on missing artifacts",
    )
    args = parser.parse_args()
    try:
        path = save_variables(
            generate_variables(REPO_ROOT, require_analysis_outputs=not args.allow_draft),
            data_dir(REPO_ROOT) / "manuscript_variables.json",
        )
    except (FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    print(f"manuscript variables written: {path}")
    tokens = json.loads(Path(path).read_text(encoding="utf-8"))
    print(f"tokens: {len(tokens)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())