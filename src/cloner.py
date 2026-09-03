"""Idempotent, parallel cloning of the repo corpus into ``repos/``.

``plan_clones`` is pure (filesystem inspection only). ``execute_plan`` clones
missing destinations in parallel via real ``git clone --quiet`` subprocess
calls (runner seam injectable for offline tests). An existing directory that
is not a git repository is reported as ``mismatch`` and left untouched — the
operator resolves it manually rather than cloning over unknown data.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.config import OperatorConfig, load_config
from src.models import CloneOutcome, ClonePlanEntry

logger = logging.getLogger(__name__)

#: Callable seam: takes the ``git clone`` argv, returns ``(returncode, stderr)``.
CloneRunner = Callable[[list[str]], tuple[int, str]]

MISMATCH_ERROR = "destination exists and is not a git repository"
_STDERR_TAIL_CHARS = 400


def plan_clones(entries: list[tuple[str, str]], repos_dir: Path) -> list[ClonePlanEntry]:
    """Compute what needs cloning. Pure: inspects the filesystem, changes nothing.

    ``dest`` missing → needed (``missing``); ``dest/.git`` a directory or
    gitlink file (worktrees/submodules) → not needed (``exists_ok``); anything
    else → needed (``exists_mismatch``).
    """
    planned: list[ClonePlanEntry] = []
    for name, clone_url in entries:
        dest = repos_dir / name
        if not dest.exists():
            needed, reason = True, "missing"
        elif (dest / ".git").is_dir() or (dest / ".git").is_file():
            needed, reason = False, "exists_ok"
        else:
            needed, reason = True, "exists_mismatch"
        planned.append(
            ClonePlanEntry(
                name=name, clone_url=clone_url, dest=str(dest), needed=needed, reason=reason
            )
        )
    planned.sort(key=lambda entry: entry.name)
    return planned


CLONE_TIMEOUT_S = 3600
"""Hard per-clone guard: even multi-GB repos finish well inside this."""


def _default_clone_runner(argv: list[str]) -> tuple[int, str]:
    """Real ``git clone`` subprocess: return ``(returncode, stderr)``."""
    logger.debug("running git: %s", argv)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=CLONE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 124, f"git clone exceeded {CLONE_TIMEOUT_S}s and was terminated"
    return proc.returncode, proc.stderr


def _execute_one(entry: ClonePlanEntry, runner: CloneRunner) -> CloneOutcome:
    """Execute a single plan row. Never raises — every failure is an outcome."""
    if not entry.needed:
        return CloneOutcome(name=entry.name, status="already_cloned", dest=entry.dest)
    if entry.reason == "exists_mismatch":
        return CloneOutcome(
            name=entry.name, status="mismatch", dest=entry.dest, error=MISMATCH_ERROR
        )
    argv = ["git", "clone", "--quiet", entry.clone_url, entry.dest]
    start = time.perf_counter()
    try:
        returncode, stderr = runner(argv)
    except Exception as exc:  # noqa: BLE001 — a runner crash is a per-repo failure
        seconds = time.perf_counter() - start
        logger.warning("clone runner failed for %s: %s", entry.name, exc)
        return CloneOutcome(
            name=entry.name, status="failed", dest=entry.dest, error=str(exc), seconds=seconds
        )
    seconds = time.perf_counter() - start
    if returncode == 0:
        return CloneOutcome(name=entry.name, status="cloned", dest=entry.dest, seconds=seconds)
    return CloneOutcome(
        name=entry.name,
        status="failed",
        dest=entry.dest,
        error=(stderr or "")[-_STDERR_TAIL_CHARS:],
        seconds=seconds,
    )


def execute_plan(
    plan: list[ClonePlanEntry], *, workers: int = 8, runner: CloneRunner | None = None
) -> list[CloneOutcome]:
    """Clone every ``needed`` plan row in parallel; results sorted by name.

    Not-needed rows become ``already_cloned`` (0.0s). ``exists_mismatch`` rows
    are never cloned over — they return ``mismatch`` with a fixed error string
    (documented; resolve manually). Runner exceptions and nonzero exits both
    produce ``failed`` outcomes; :func:`execute_plan` itself never raises.
    """
    runner = runner if runner is not None else _default_clone_runner
    outcomes: list[CloneOutcome] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {entry: pool.submit(_execute_one, entry, runner) for entry in plan}
        for entry, future in futures.items():
            try:
                outcomes.append(future.result())
            except Exception as exc:  # noqa: BLE001 — never propagate to the caller
                logger.warning("clone execution crashed for %s: %s", entry.name, exc)
                outcomes.append(
                    CloneOutcome(name=entry.name, status="failed", dest=entry.dest, error=str(exc))
                )
    outcomes.sort(key=lambda outcome: outcome.name)
    return outcomes


def clone_corpus(
    registry: dict, project_root: Path, *, workers: int = 8, runner: CloneRunner | None = None
) -> list[CloneOutcome]:
    """Plan + execute clones for the registry against the configured repos dir.

    ``registry`` is the ``repo_registry.json`` artifact (``repos`` entries are
    ``RepoMeta`` ``to_dict`` shapes; raw :class:`RepoMeta` dataclasses are also
    tolerated). The target directory comes from ``load_config(project_root)``
    and is created if missing. This is the function scripts call.
    """
    config = load_config(project_root)
    target = project_root / config.repos_dir
    target.mkdir(parents=True, exist_ok=True)
    entries: list[tuple[str, str]] = []
    for item in registry.get("repos", []):
        if isinstance(item, dict):
            name, url = item.get("name"), item.get("clone_url")
        else:  # tolerate raw RepoMeta instances alongside to_dict shapes
            name, url = getattr(item, "name", None), getattr(item, "clone_url", None)
        if not name or not url:
            raise ValueError(f"registry entry missing name/clone_url: {item!r}")
        entries.append((str(name), str(url)))
    plan = plan_clones(entries, target)
    return execute_plan(plan, workers=workers, runner=runner)