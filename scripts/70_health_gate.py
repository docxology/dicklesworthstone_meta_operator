#!/usr/bin/env python3
"""Binary go/no-go health gate over the whole artifact tree.

Checks registry, clone completeness, upstream sync, inventory coverage, and
dashboard/catalog presence; writes ``output/data/health_gate.json``:

    uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/70_health_gate.py
    uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/70_health_gate.py --from-github

``--from-github`` cross-checks the registry against a fresh API enumeration
(network); ``--expected N`` pins an expected repo count.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config  # noqa: E402
from src.health_gate import load_gate, run_gate, save_gate  # noqa: E402


def main() -> int:
    """Run the gate, persist the report, exit 0 only on GO."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", type=int, help="expected registry repo count")
    parser.add_argument(
        "--from-github",
        action="store_true",
        help="derive the expected count from a fresh GitHub enumeration",
    )
    args = parser.parse_args()

    expected = args.expected
    if args.from_github:
        from src.github_client import enumerate_repos

        config = load_config(REPO_ROOT)
        expected = len(
            enumerate_repos(config.github_user, include_forks=config.include_forks)
        )
        print(f"expected repo count from GitHub: {expected}")

    report = run_gate(REPO_ROOT, expected_count=expected)
    path = save_gate(report, REPO_ROOT)
    for check in report.checks:
        marker = "PASS" if check.passed else "FAIL"
        print(f"  [{marker}] {check.check_id}: {check.detail}")
    print(f"gate report written: {path}")
    verdict = "GO" if report.passed else "NO-GO"
    print(f"HEALTH GATE: {verdict}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
