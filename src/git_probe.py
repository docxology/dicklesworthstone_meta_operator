from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0


def run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Probe an explicit checkout; timeout is an unsuccessful exit-124 result."""
    root = Path(root).resolve()
    marker = root / ".git"
    argv = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
            f"--git-dir={marker}", f"--work-tree={root}", *args]
    if not marker.is_dir() and not marker.is_file():
        return subprocess.CompletedProcess(argv, 1, "", "target has no .git marker")
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    try:
        return subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, check=False, timeout=DEFAULT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", "git probe timed out")
