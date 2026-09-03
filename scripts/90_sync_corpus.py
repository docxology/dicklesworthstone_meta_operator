#!/usr/bin/env python3
"""Sync every clone with its upstream: ``git pull --ff-only`` per repo.

The corpus is a mirror: fast-forward-only pulls can never create local
merge commits. Repos that cannot pull (e.g. empty upstreams, where the
tracking ref does not exist) are reported as typed run failures — they
remain upstream-ok in verification (state ``unborn``):

    uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/90_sync_corpus.py

With ``--submodules``, repos containing ``.gitmodules`` additionally run
``git submodule update --init --recursive``. Writes run artifacts like
script 50 and exits 1 when any repo failed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config  # noqa: E402
from src.orchestrator import run_and_save, summarize  # noqa: E402
from src.upstream_check import find_unborn  # noqa: E402
from src.registry import load_registry, registry_metas  # noqa: E402


def main() -> int:
    """Pull every clone (fast-forward-only); exit 1 on any failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--submodules",
        action="store_true",
        help="also run `git submodule update --init --recursive` where .gitmodules exists",
    )
    parser.add_argument("--no-forks", action="store_true", help="skip fork repos")
    parser.add_argument("--workers", type=int, help="parallel repos (default: config)")
    parser.add_argument("--timeout-s", type=int, dest="timeout_s", help="per-repo timeout")
    args = parser.parse_args()

    config = load_config(REPO_ROOT)
    registry = load_registry(REPO_ROOT)
    metas = registry_metas(registry)
    names = sorted(metas)
    if args.no_forks:
        names = [n for n in names if not metas[n].fork]
    if not names:
        print("registry is empty — run scripts/10_build_registry.py first")
        return 1
    repos_dir = REPO_ROOT / config.repos_dir
    unborn = find_unborn(names, repos_dir)
    names = [n for n in names if n not in set(unborn)]
    if unborn:
        print(f"skipping {len(unborn)} unborn repos (empty upstream, nothing to pull): "
              + ", ".join(unborn))

    failed = False

    def run_pass(names_: list[str], command: str, label: str) -> None:
        nonlocal failed
        if not names_:
            print(f"{label}: nothing to do")
            return
        print(f"{label}: running in {len(names_)} repos: {command}")
        run_id, artifact = run_and_save(
            names_,
            command,
            project_root=REPO_ROOT,
            selector_desc=label,
            workers=args.workers or config.run_workers,
            timeout_s=args.timeout_s or config.run_timeout_s,
            tail_bytes=config.stream_tail_bytes,
        )
        summary = summarize(artifact)
        print(
            f"{label} run {run_id}: {summary['ok']} ok / {summary['failed']} failed / "
            f"{summary['timed_out']} timed out / {summary['skipped']} skipped"
        )
        if summary["failed"] or summary["timed_out"]:
            failed = True

    run_pass(names, "git pull --ff-only", "pull")
    if args.submodules:
        repos_dir = REPO_ROOT / config.repos_dir
        with_modules = [
            name for name in names if (repos_dir / name / ".gitmodules").is_file()
        ]
        run_pass(
            with_modules, "git submodule update --init --recursive", "submodules"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
