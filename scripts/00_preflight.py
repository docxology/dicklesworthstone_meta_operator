#!/usr/bin/env python3
"""Pre-flight check for meta-operator prerequisites.

Verifies the toolchain the pipeline needs (gh CLI + auth, git, python >= 3.11)
and that ``repos/`` is writable. Run before any pipeline stage:

    uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/00_preflight.py

``--offline`` skips the gh auth check for airgapped/CI runs.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    """Check prerequisites; return 0 when all pass, 1 with diagnostics otherwise."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the gh auth check (no network)",
    )
    args = parser.parse_args()

    problems: list[str] = []
    if sys.version_info < (3, 11):
        problems.append(f"python >= 3.11 required, running {sys.version.split()[0]}")
    if shutil.which("gh") is None:
        problems.append("gh CLI not found — install https://cli.github.com")
    elif not args.offline:
        proc = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        if proc.returncode != 0:
            problems.append(
                "gh auth check failed — run: gh auth login\n" + proc.stderr.strip()
            )
    if shutil.which("git") is None:
        problems.append("git not found")

    repos_dir = REPO_ROOT / "repos"
    repos_dir.mkdir(exist_ok=True)
    probe = repos_dir / ".write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        problems.append(f"repos dir not writable: {exc}")

    if problems:
        sys.stderr.write(
            "PREFLIGHT FAILED\n" + "\n".join(f"- {p}" for p in problems) + "\n"
        )
        return 1
    suffix = "gh auth not checked (--offline)" if args.offline else "gh auth ok"
    print(f"preflight OK: gh, git, python>=3.11, repos/ writable, {suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
