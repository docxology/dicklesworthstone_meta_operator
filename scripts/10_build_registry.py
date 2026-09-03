#!/usr/bin/env python3
"""Build the repo registry from the GitHub API (network required).

Enumerates every repository of the configured ``github_user`` and writes
``output/data/repo_registry.json``:

    uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/10_build_registry.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config  # noqa: E402
from src.github_client import enumerate_repos  # noqa: E402
from src.registry import build_registry, save_registry  # noqa: E402


def main() -> int:
    """Enumerate repos and persist the registry artifact."""
    config = load_config(REPO_ROOT)
    metas = enumerate_repos(config.github_user, include_forks=config.include_forks)
    registry = build_registry(
        metas, github_user=config.github_user, include_forks=config.include_forks
    )
    path = save_registry(registry, REPO_ROOT)
    forks = sum(1 for meta in metas if meta.fork)
    print(f"registry written: {path}")
    print(
        f"repos: {len(metas)} (include_forks={config.include_forks}, {forks} forks)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
