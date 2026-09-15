"""code_meta_analysis integration lane: orchestration-only corpus analysis.

Pipeline position: an orchestration lane of stage 50 (``--auto cma-analyze``).
It invokes the code_meta_analysis checkout's lanes CLI (``scripts/lanes.py``)
per repo, parses the two signals the dashboard surfaces (issue count from the
``issues`` lane, dependency-graph centrality from the ``deps`` lane), and
records per-repo results in the run artifact under a ``cma`` mapping.

Failure discipline: a cma failure for one repo is a failed ``RunResult`` row
plus a ``status: failed`` cma row — never a pipeline abort. A repo with no
clone is skipped by ``execute_runs`` and gets no cma row (the dashboard
renders "no cma report yet").

CLI surfaces consumed (treated as stable; cwd = the cma checkout so ``uv run``
resolves cma's own environment):
- ``uv run python scripts/lanes.py issues <repo> --json --out <dir>``
  (writes ``<dir>/<repo>_issues.json``)
- ``uv run python scripts/lanes.py deps <repo> --json`` (prints a JSON object
  with ``summary`` and ``central_files``)

Per-lane observability: the ``issues`` lane succeeded iff its
``<repo>_issues.json`` exists and parses; the ``deps`` lane succeeded iff the
combined row's ``stdout_tail`` parses as the expected JSON shape. If either
lane times out, both lane statuses conservatively read as failed in the cma
row (the combined row carries ``timed_out: true``).
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src import project_paths
from src.jsonio import write_json as _write_json
from src.models import RunResult, to_dict
from src.orchestrator import _tail, execute_runs, plan_runs

logger = logging.getLogger(__name__)

CMA_AUTO_KEY = "cma-analyze"
CMA_COMMAND_LABEL = "cma:issues+deps"
LANES_ENTRY = Path("scripts") / "lanes.py"

LANE_OK = "ok"
LANE_FAILED = "failed"

CMA_LANES = ("issues", "deps")


@dataclass(frozen=True)
class LaneOutcome:
    """Outcome of one cma lane subprocess; never raises upstream."""

    exit_code: int | None
    timed_out: bool
    seconds: float
    stdout_tail: str
    stderr_tail: str


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


def resolve_cma_dir(config: Any, project_root: Path) -> Path:
    """Resolve the code_meta_analysis checkout path from ``config.cma_dir``.

    Relative to ``project_root``. Raises ``FileNotFoundError`` with a fix hint
    when the checkout (or its lanes CLI) is missing — a configuration error
    aborts the lane up front; per-repo cma failures never do.
    """
    root = Path(project_root).resolve()
    candidate = (root / config.cma_dir).resolve()
    entry = candidate / LANES_ENTRY
    if not entry.is_file():
        raise FileNotFoundError(
            f"cma checkout not found at {candidate} (cma_dir={config.cma_dir!r}) — "
            "clone code_meta_analysis there or set cma_dir in data/operator_config.yaml"
        )
    return candidate


# ---------------------------------------------------------------------------
# Pure parsing / command construction
# ---------------------------------------------------------------------------


def lane_argv(
    lane: str, repo_path: Path, cma_dir: Path, out_dir: Path | None = None
) -> list[str]:
    """Argv for one cma lane, to be run with cwd ``cma_dir`` (pure)."""
    if lane not in CMA_LANES:
        raise ValueError(f"lane must be one of {list(CMA_LANES)}, got {lane!r}")
    repo = Path(repo_path).resolve()
    argv = ["uv", "run", "python", str(LANES_ENTRY), lane, str(repo), "--json"]
    if lane == "issues":
        argv += ["--out", str(Path(out_dir).resolve())]
    return argv


def parse_deps_report(stdout: str) -> dict | None:
    """Parse the ``deps`` lane stdout JSON into its dict, else ``None``.

    Tolerates noise lines around the JSON object (uv warnings, progress) by
    scanning from the first ``{`` to the last ``}``.
    """
    text = (stdout or "").strip()
    if not text:
        return None
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            raw = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(raw, dict) and isinstance(raw.get("central_files"), list):
            return raw
    return None


def read_issues_file(path: Path) -> list | None:
    """Read a cma ``<repo>_issues.json`` report; its ``issues`` list, else None."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if isinstance(raw, dict) and isinstance(raw.get("issues"), list):
        return raw["issues"]
    return None


def build_cma_rows(results: list[RunResult], out_dir: Path) -> dict[str, dict]:
    """Derive per-repo cma rows from executed results + lane artifacts.

    Reads each repo's ``<name>_issues.json`` under ``out_dir`` and parses the
    combined row's ``stdout_tail`` for the deps report. Repos skipped for a
    missing clone produce no row. Sorted by name; deterministic.
    """
    rows: dict[str, dict] = {}
    for r in results:
        if r.skipped:
            continue
        issues = None
        if r.exit_code == 0 and not r.timed_out:
            issues = read_issues_file(Path(out_dir) / f"{r.name}_issues.json")
        deps = None
        if not r.timed_out:
            deps = parse_deps_report(r.stdout_tail)
        lanes = {
            "issues": LANE_OK if issues is not None else LANE_FAILED,
            "deps": LANE_OK if deps is not None else LANE_FAILED,
        }
        central = (deps.get("central_files") or [None])[0] if deps else None
        rows[r.name] = {
            "issues_count": len(issues) if issues is not None else None,
            "central_file": str(central.get("path")) if central else None,
            "coupling": central.get("coupling") if central else None,
            "lanes": lanes,
            "status": (
                "ok"
                if lanes["issues"] == LANE_OK and lanes["deps"] == LANE_OK
                else "failed"
            ),
        }
    return dict(sorted(rows.items()))


# ---------------------------------------------------------------------------
# Subprocess boundary
# ---------------------------------------------------------------------------


def _run_lane(
    argv: list[str], cwd: Path, *, timeout_s: int, tail_bytes: int
) -> LaneOutcome:
    """Run one cma lane via subprocess; never raises."""
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return LaneOutcome(
            exit_code=proc.returncode,
            timed_out=False,
            seconds=time.monotonic() - started,
            stdout_tail=_tail(proc.stdout, tail_bytes),
            stderr_tail=_tail(proc.stderr, tail_bytes),
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("cma lane timed out: %s", " ".join(argv))
        return LaneOutcome(
            exit_code=None,
            timed_out=True,
            seconds=time.monotonic() - started,
            stdout_tail=_tail(exc.stdout, tail_bytes),
            stderr_tail=_tail(exc.stderr, tail_bytes),
        )
    except Exception as exc:  # noqa: BLE001 — lane must never raise
        logger.warning("cma lane failed to start: %s (%s)", " ".join(argv), exc)
        return LaneOutcome(
            exit_code=None,
            timed_out=False,
            seconds=time.monotonic() - started,
            stdout_tail="",
            stderr_tail=str(exc),
        )


def build_cma_runner(
    cma_dir: Path, out_dir: Path, *, timeout_s: int, tail_bytes: int
) -> Callable[[str, str, Path], RunResult]:
    """Combined per-repo runner: issues lane then deps lane, both from ``cma_dir``.

    Matches the ``execute_runs`` runner seam. The combined ``RunResult``:
    ``stdout_tail`` carries the deps lane stdout (parsed later for centrality),
    ``stderr_tail`` joins both lanes' tails, ``seconds`` sums both, and the
    combined outcome is ``timed_out`` if either lane timed out, otherwise the
    first nonzero lane exit code in issues→deps order.
    """

    def runner(name: str, effective_cmd: str, repo_path: Path) -> RunResult:
        repo = Path(repo_path).resolve()
        issues = _run_lane(
            lane_argv("issues", repo, cma_dir, out_dir),
            cma_dir,
            timeout_s=timeout_s,
            tail_bytes=tail_bytes,
        )
        deps = _run_lane(
            lane_argv("deps", repo, cma_dir),
            cma_dir,
            timeout_s=timeout_s,
            tail_bytes=tail_bytes,
        )
        timed_out = issues.timed_out or deps.timed_out
        exit_code: int | None = None
        if not timed_out:
            exit_code = 0
            for lane in (issues, deps):
                if lane.exit_code != 0:
                    exit_code = lane.exit_code
                    break
        stderr = issues.stderr_tail
        if deps.stderr_tail:
            stderr = (stderr + "\n" if stderr else "") + "[cma deps]\n" + deps.stderr_tail
        return RunResult(
            name=name,
            command=effective_cmd,
            exit_code=exit_code,
            timed_out=timed_out,
            skipped=False,
            skip_reason="",
            seconds=issues.seconds + deps.seconds,
            stdout_tail=deps.stdout_tail,
            stderr_tail=_tail(stderr, tail_bytes),
        )

    return runner


# ---------------------------------------------------------------------------
# Run entry point
# ---------------------------------------------------------------------------


def run_cma_analyze(
    names: list[str],
    *,
    project_root: Path,
    config: Any,
    selector_desc: str,
    run_id: str | None = None,
    workers: int | None = None,
    timeout_s: int | None = None,
    tail_bytes: int | None = None,
    runner: Callable[..., RunResult] | None = None,
    repos_dir: Path | None = None,
) -> tuple[str, dict]:
    """Run the cma lanes over ``names`` and persist the run artifact.

    Artifact shape: the cross-builder run shape plus ``"cma"`` (per-repo rows
    from :func:`build_cma_rows`). Per-repo issue reports are kept under
    ``output/data/cma/<run_id>/``. ``runner`` may be injected for tests (a
    fake cma CLI writing the lane artifacts); the default runs the real cma
    lanes CLI via ``uv``.
    """
    cma_dir = resolve_cma_dir(config, project_root)
    root = Path(project_root).resolve()
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = project_paths.data_dir(root) / "cma" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    effective_runner = runner or build_cma_runner(
        cma_dir,
        out_dir,
        timeout_s=timeout_s or config.run_timeout_s,
        tail_bytes=tail_bytes or config.stream_tail_bytes,
    )
    results = execute_runs(
        plan_runs(names, CMA_COMMAND_LABEL),
        repos_dir or project_paths.repos_dir(root),
        runner=effective_runner,
        workers=workers or config.run_workers,
    )
    artifact = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": CMA_COMMAND_LABEL,
        "selector": selector_desc,
        "repos": [to_dict(r) for r in results],
        "cma": build_cma_rows(results, out_dir),
    }
    _write_json(project_paths.runs_dir(root) / run_id / "results.json", artifact)
    return run_id, artifact


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def render_cma_section(cma_rows: dict[str, dict]) -> str:
    """Deterministic markdown cma section appended to the stage-50 report."""
    if not cma_rows:
        return ""
    lines = ["", "## cma (code_meta_analysis)", ""]
    lines.append(
        "| Repo | Issues | Top central file | Coupling | Issues lane | Deps lane | Status |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for name in sorted(cma_rows):
        row = cma_rows[name] or {}
        count = row.get("issues_count")
        coupling = row.get("coupling")
        lanes = row.get("lanes") or {}
        lines.append(
            f"| {name} | {count if count is not None else '—'} "
            f"| {row.get('central_file') or '—'} "
            f"| {coupling if coupling is not None else '—'} "
            f"| {lanes.get('issues', '—')} | {lanes.get('deps', '—')} "
            f"| {row.get('status', '—')} |"
        )
    return "\n".join(lines).rstrip("\n") + "\n"