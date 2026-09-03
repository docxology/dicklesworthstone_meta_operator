#!/usr/bin/env python3
"""Run one command across selected repos and persist the run.

Selectors narrow the corpus; the command is plain argv (no shell) run in each
clone with a per-repo timeout. Results land in
``output/data/runs/<run_id>/results.json`` plus a markdown report under
``output/reports/``:

    uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/50_orchestrate.py \
        --auto test --language Python --limit 5
    uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/50_orchestrate.py \
        --command "git log -1 --format=%h %s" --set franken_engine
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config  # noqa: E402
from src.inventory import build_inventory  # noqa: E402
from src.jsonio import read_json, write_text  # noqa: E402
from src.models import AUTO_COMMAND_KEYS  # noqa: E402
from src.orchestrator import (  # noqa: E402
    SelectorSpec,
    filter_repos,
    render_run_report,
    resolve_auto,
    run_and_save,
    summarize,
)
from src.project_paths import INVENTORY, data_dir, reports_dir  # noqa: E402
from src.registry import load_registry, registry_metas  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    """CLI surface for cross-corpus command runs."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--command", help="exact argv command to run in each repo")
    group.add_argument(
        "--auto",
        choices=sorted(AUTO_COMMAND_KEYS),
        help="use each repo's auto-detected command for this key",
    )
    parser.add_argument("--set", nargs="+", dest="names", help="explicit repo names")
    parser.add_argument("--language", help="filter by primary language")
    parser.add_argument("--min-loc", type=int, default=0, help="minimum total LOC")
    parser.add_argument("--exclude", nargs="*", default=[], help="repo names to skip")
    parser.add_argument("--limit", type=int, help="cap the number of repos")
    parser.add_argument(
        "--sort",
        default="name",
        choices=["name", "size", "loc", "recent"],
        help="selection order before --limit",
    )
    parser.add_argument(
        "--no-forks",
        action="store_true",
        help="skip fork repos (registry fork flag)",
    )
    parser.add_argument("--workers", type=int, help="parallel repos (default: config)")
    parser.add_argument("--timeout-s", type=int, dest="timeout_s", help="per-repo timeout")
    parser.add_argument("--tail-bytes", type=int, help="captured stream tail size")
    return parser


def main() -> int:
    """Select repos, run the command, persist + report the run."""
    args = build_parser().parse_args()
    config = load_config(REPO_ROOT)

    try:
        inventory = read_json(data_dir(REPO_ROOT) / INVENTORY, required=True)
    except FileNotFoundError:
        sys.stderr.write(
            "inventory missing — run scripts/40_inventory.py first "
            f"(expected {data_dir(REPO_ROOT) / INVENTORY})\n"
        )
        return 1
    profiles = {entry["name"]: entry for entry in inventory["repos"]}

    # Merge registry metadata (size for --sort size, fork for --no-forks) so
    # the pure selector sees one flat profile per repo.
    metas = registry_metas(load_registry(REPO_ROOT))
    merged = {
        name: {
            **profile,
            "size_kb": metas[name].size_kb if name in metas else 0,
            "fork": bool(metas[name].fork) if name in metas else False,
        }
        for name, profile in profiles.items()
    }

    selector = SelectorSpec(
        set_=tuple(args.names) if args.names else None,
        language=args.language,
        min_loc=args.min_loc,
        exclude=tuple(args.exclude or ()),
        sort=args.sort,
        forks=False if args.no_forks else None,
    )
    names = filter_repos(merged, selector)
    overrides: dict[str, str] = {}
    if args.auto is not None:
        names, overrides, skipped = resolve_auto(names, merged, args.auto)
        if skipped:
            print(
                f"skipping {len(skipped)} repos without auto '{args.auto}': "
                + ", ".join(skipped[:10])
            )
        if not names:
            print(f"no selected repo has an auto '{args.auto}' command")
            return 0
        command = f"auto:{args.auto}"
    else:
        command = str(args.command)

    if not names:
        print("no repos match the selector")
        return 0

    selector_desc = (
        f"set={list(args.names) if args.names else 'all'} lang={args.language or '*'} "
        f"min_loc={args.min_loc} sort={args.sort} limit={args.limit or '*'}"
    )
    print(f"running in {len(names)} repos: {command}")
    run_id, artifact = run_and_save(
        names,
        command,
        project_root=REPO_ROOT,
        selector_desc=selector_desc,
        workers=args.workers or config.run_workers,
        timeout_s=args.timeout_s or config.run_timeout_s,
        tail_bytes=args.tail_bytes or config.stream_tail_bytes,
        overrides=overrides or None,
    )
    summary = summarize(artifact)
    report_path = write_text(
        reports_dir(REPO_ROOT) / f"{run_id}.md", render_run_report(artifact, summary)
    )
    print(
        f"run {run_id}: {summary['ok']} ok / {summary['failed']} failed / "
        f"{summary['timed_out']} timed out / {summary['skipped']} skipped"
    )
    print(f"report: {report_path}")
    executed = sum(1 for r in artifact["repos"] if not r.get("skipped"))
    if executed == 0:
        print("nothing executed — every selected repo was skipped")
        return 1
    return 0 if summary["failed"] == 0 and summary["timed_out"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
