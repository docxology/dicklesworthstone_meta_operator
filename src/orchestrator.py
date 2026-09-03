"""Orchestration layer: run one command across selected repos with bounded parallelism.

Pipeline position: consumes repo selection criteria (``SelectorSpec``) plus a repo
profile map, plans per-repo runs, executes them in a thread pool with a hard
per-run timeout, and persists each run as ``output/data/runs/<RUN_ID>/results.json``.

Notes for operators:
- Commands are split with ``shlex.split`` and executed as a plain argv list, so
  shell syntax (pipes, ``&&``, redirections) is NOT interpreted. Complex commands
  must be wrapped explicitly, e.g. ``sh -c "pytest -q | tail -20"``.
- ``execute_runs`` never raises: every failure mode (missing clone, timeout,
  unexpected exception) degrades to a well-formed ``RunResult``.
- A ``runner`` callable can be injected for tests; the default runner is
  ``subprocess.run``.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.models import AUTO_COMMAND_KEYS, RunResult, to_dict
from src.jsonio import write_json as _write_json

logger = logging.getLogger(__name__)



VALID_SORTS: frozenset[str] = frozenset({"name", "size", "loc", "recent"})


@dataclass(frozen=True)
class SelectorSpec:
    """Criteria for choosing which repos a run targets.

    ``set_`` restricts to an explicit name set (``None`` = all); ``language``
    matches the profile's primary language (``None`` = no filter); ``min_loc``
    filters on ``total_loc``; ``exclude`` removes names outright; ``limit``
    truncates after sorting; ``sort`` picks the ordering key.
    """

    set_: tuple[str, ...] | None = None
    language: str | None = None
    min_loc: int = 0
    exclude: tuple[str, ...] = ()
    limit: int | None = None
    sort: str = "name"
    forks: bool | None = None  # None = no fork filtering

    def __post_init__(self) -> None:
        if self.sort not in VALID_SORTS:
            raise ValueError(f"sort must be one of {sorted(VALID_SORTS)}, got {self.sort!r}")


def _primary_language(profile: dict[str, Any]) -> Any:
    """Primary language of a profile dict (RepoProfile.to_dict shape)."""
    if "primary_language" in profile:
        return profile["primary_language"]
    return profile.get("language")


def _metric(profile: dict[str, Any], sort: str) -> Any:
    """Sort metric for a profile; missing keys degrade to 0 / empty string."""
    if sort == "size":
        return profile.get("size_kb", 0) or 0
    if sort == "loc":
        return profile.get("total_loc", 0) or 0
    if sort == "recent":
        return profile.get("last_commit_date") or ""
    return ""


def filter_repos(profiles: dict[str, dict], selector: SelectorSpec) -> list[str]:
    """Pure selection: filter profiles by ``selector`` and return sorted names.

    Filters applied in order: set membership, language equality, ``min_loc``,
    exclusion. Sort orders: ``name`` alphabetical; ``size`` by ``size_kb`` desc;
    ``loc`` by ``total_loc`` desc; ``recent`` by ``last_commit_date`` desc — all
    with name as ascending tiebreaker. ``limit`` truncates AFTER sorting.
    """
    names = [n for n in profiles if n not in selector.exclude]
    if selector.set_ is not None:
        wanted = set(selector.set_)
        names = [n for n in names if n in wanted]
    if selector.language is not None:
        names = [n for n in names if _primary_language(profiles[n]) == selector.language]
    if selector.forks is not None:
        names = [n for n in names if bool(profiles[n].get("fork")) is selector.forks]
    if selector.min_loc > 0:
        names = [n for n in names if (profiles[n].get("total_loc", 0) or 0) >= selector.min_loc]
    # Stable two-pass sort: name ascending first (tiebreaker), then metric desc.
    names.sort()
    if selector.sort != "name":
        names.sort(key=lambda n: _metric(profiles[n], selector.sort), reverse=True)
    if selector.limit is not None:
        names = names[: selector.limit]
    return names


def resolve_auto(
    names: list[str], profiles: dict[str, dict], key: str
) -> tuple[list[str], dict[str, str], list[str]]:
    """Resolve an auto-command key against selected repo profiles (pure).

    Returns ``(capable_names, overrides, skipped)``: repos whose profile's
    ``auto_cmds`` provide ``key`` get that command (sorted names, matching
    overrides mapping); the rest are reported as skipped (sorted).
    """
    if key not in AUTO_COMMAND_KEYS:
        raise ValueError(f"unknown auto-command key: {key!r}")
    capable = {
        name: cmds[key]
        for name, cmds in ((n, profiles[n].get("auto_cmds") or {}) for n in names)
        if cmds.get(key)
    }
    return sorted(capable), capable, sorted(set(names) - set(capable))


def plan_runs(names: list[str], command: str) -> list[tuple[str, str]]:
    """Plan rows as ``(name, command)`` pairs sorted by name.

    The command is identical for every repo by design; per-repo overrides happen
    at execution time via the ``overrides`` mapping in ``execute_runs``.
    """
    return [(name, command) for name in sorted(names)]


def _tail(stream: Any, tail_bytes: int) -> str:
    """Last ``tail_bytes`` of a stream, decoded UTF-8 with replacement.

    Accepts ``str``, ``bytes``, or ``None`` (-> empty string).
    """
    if stream is None:
        return ""
    data = stream if isinstance(stream, bytes) else str(stream).encode("utf-8")
    if len(data) > tail_bytes:
        data = data[-tail_bytes:]
    return data.decode("utf-8", errors="replace")


def _default_runner(
    name: str, effective_cmd: str, repo_path: Path, *, timeout_s: int, tail_bytes: int
) -> RunResult:
    """Run ``effective_cmd`` in ``repo_path`` via subprocess; never raises.

    On timeout: ``exit_code=None``, ``timed_out=True``, tails from whatever the
    child produced. On any other exception: ``exit_code=None`` with the error
    text in ``stderr_tail``.
    """
    started = time.monotonic()
    try:
        proc = subprocess.run(
            shlex.split(effective_cmd),
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        seconds = time.monotonic() - started
        return RunResult(
            name=name,
            command=effective_cmd,
            exit_code=proc.returncode,
            timed_out=False,
            skipped=False,
            skip_reason="",
            seconds=seconds,
            stdout_tail=_tail(proc.stdout, tail_bytes),
            stderr_tail=_tail(proc.stderr, tail_bytes),
        )
    except subprocess.TimeoutExpired as exc:
        seconds = time.monotonic() - started
        logger.warning("run timed out in %s: %s", name, effective_cmd)
        return RunResult(
            name=name,
            command=effective_cmd,
            exit_code=None,
            timed_out=True,
            skipped=False,
            skip_reason="",
            seconds=seconds,
            stdout_tail=_tail(exc.stdout, tail_bytes),
            stderr_tail=_tail(exc.stderr, tail_bytes),
        )
    except Exception as exc:  # noqa: BLE001 — orchestration must never raise
        logger.warning("run failed to start in %s: %s (%s)", name, effective_cmd, exc)
        return RunResult(
            name=name,
            command=effective_cmd,
            exit_code=None,
            timed_out=False,
            skipped=False,
            skip_reason="",
            seconds=time.monotonic() - started,
            stdout_tail="",
            stderr_tail=str(exc),
        )


def execute_runs(
    plan: list[tuple[str, str]],
    repos_dir: Path,
    *,
    workers: int = 6,
    timeout_s: int = 600,
    tail_bytes: int = 20000,
    overrides: dict[str, str] | None = None,
    runner: Callable[..., RunResult] | None = None,
) -> list[RunResult]:
    """Execute the plan across repos with bounded parallelism; never raises.

    Per ``(name, cmd)``: the effective command is ``overrides.get(name, cmd)``
    run with cwd ``repos_dir/name``. A repo without ``.git`` is skipped with
    reason ``"missing clone"``. ``runner`` may be injected for tests; when given
    it is called as ``runner(name, effective_cmd, repo_path)`` (keyword arg
    ``timeout_s``/``tail_bytes`` forwarded when accepted) and must return a
    ``RunResult``; its exceptions are handled by the same never-raise policy.
    Results are sorted by name.
    """
    overrides = overrides or {}
    if not plan:
        return []
    if runner is None:
        call_runner: Callable[..., RunResult] = (
            lambda name, cmd, path: _default_runner(
                name, cmd, path, timeout_s=timeout_s, tail_bytes=tail_bytes
            )
        )
    else:
        call_runner = runner

    def run_one(item: tuple[str, str]) -> RunResult:
        name, cmd = item
        effective_cmd = overrides.get(name, cmd)
        repo_path = repos_dir / name
        if not (repo_path / ".git").exists():
            return RunResult(
                name=name,
                command=effective_cmd,
                exit_code=None,
                timed_out=False,
                skipped=True,
                skip_reason="missing clone",
                seconds=0.0,
                stdout_tail="",
                stderr_tail="",
            )
        try:
            return call_runner(name, effective_cmd, repo_path)
        except subprocess.TimeoutExpired as exc:
            return RunResult(
                name=name,
                command=effective_cmd,
                exit_code=None,
                timed_out=True,
                skipped=False,
                skip_reason="",
                seconds=float(timeout_s),
                stdout_tail=_tail(exc.stdout, tail_bytes),
                stderr_tail=_tail(exc.stderr, tail_bytes),
            )
        except Exception as exc:  # noqa: BLE001 — orchestration must never raise
            logger.warning("run errored in %s: %s (%s)", name, effective_cmd, exc)
            return RunResult(
                name=name,
                command=effective_cmd,
                exit_code=None,
                timed_out=False,
                skipped=False,
                skip_reason="",
                seconds=0.0,
                stdout_tail="",
                stderr_tail=str(exc),
            )

    max_workers = max(1, min(workers, len(plan)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(run_one, plan))
    return sorted(results, key=lambda r: r.name)


def run_and_save(
    names: list[str],
    command: str,
    *,
    project_root: Path,
    selector_desc: str,
    run_id: str | None = None,
    **execute_kwargs: Any,
) -> tuple[str, dict]:
    """Execute the run and persist ``results.json`` under the runs directory.

    ``execute_kwargs`` are forwarded to ``execute_runs`` (``repos_dir`` may be
    overridden there; it defaults to ``<project_root>/repos``). Returns
    ``(run_id, artifact)`` where the artifact matches the cross-builder shape
    ``{"run_id", "generated_at", "command", "selector", "repos"}``.
    """
    from src import project_paths

    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    repos_dir = execute_kwargs.pop("repos_dir", None) or project_paths.repos_dir(project_root)
    results = execute_runs(plan_runs(names, command), repos_dir, **execute_kwargs)
    artifact = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": command,
        "selector": selector_desc,
        "repos": [to_dict(r) for r in results],
    }
    _write_json(project_paths.runs_dir(project_root) / run_id / "results.json", artifact)
    return run_id, artifact


def summarize(artifact: dict) -> dict:
    """Pure aggregate of a run artifact: counts, failures, slowest runs.

    ``ok`` = exit 0 and not skipped; ``failed`` = not skipped and exit code not
    in ``(0,)`` (timed-out runs have ``exit_code=None`` and are counted here
    too); ``timed_out`` ⊆ ``failed``. ``failures`` and ``slowest`` (top 5) are
    sorted and capped as specified.
    """
    repos = artifact.get("repos", [])
    ok = sum(
        1
        for r in repos
        if not r.get("skipped") and r.get("exit_code") == 0 and not r.get("timed_out")
    )
    failed = [r for r in repos if not r.get("skipped") and r.get("exit_code") not in (0,)]
    skipped = sum(1 for r in repos if r.get("skipped"))
    return {
        "total": len(repos),
        "ok": ok,
        "failed": len(failed),
        "timed_out": sum(1 for r in repos if r.get("timed_out")),
        "skipped": skipped,
        "failures": [
            {"name": r["name"], "exit_code": r["exit_code"]}
            for r in sorted(failed, key=lambda r: r["name"])
        ],
        "slowest": [
            {"name": r["name"], "seconds": r["seconds"]}
            for r in sorted(repos, key=lambda r: (-r["seconds"], r["name"]))[:5]
        ],
    }


def _fence(text: str, cap: int = 1200) -> str:
    """Render text in a fenced code block, capped at ``cap`` characters."""
    clipped = text[:cap]
    if not clipped.strip():
        clipped = "(no stderr output)"
    return f"```text\n{clipped}\n```"


def render_run_report(artifact: dict, summary: dict) -> str:
    """Deterministic markdown report for one run: header, summary, table, failures."""
    lines: list[str] = []
    lines.append(f"# Run Report: {artifact['run_id']}")
    lines.append("")
    lines.append(f"- **Command:** `{artifact['command']}`")
    lines.append(f"- **Selector:** {artifact['selector']}")
    lines.append(f"- **Generated:** {artifact['generated_at']}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for key in ("total", "ok", "failed", "timed_out", "skipped"):
        lines.append(f"- **{key}:** {summary[key]}")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| Repo | Exit | Seconds | Timed Out | Skipped |")
    lines.append("|---|---|---|---|---|")
    stderr_by_name: dict[str, str] = {}
    for r in sorted(artifact.get("repos", []), key=lambda r: r["name"]):
        stderr_by_name[r["name"]] = r.get("stderr_tail", "")
        lines.append(
            f"| {r['name']} | {r['exit_code']} | {r['seconds']:.3f} | "
            f"{str(r.get('timed_out', False)).lower()} | {str(r.get('skipped', False)).lower()} |"
        )
    lines.append("")
    lines.append("## Failures")
    lines.append("")
    if not summary["failures"]:
        lines.append("None.")
    else:
        for failure in summary["failures"]:
            name = failure["name"]
            lines.append(f"### {name} (exit {failure['exit_code']})")
            lines.append("")
            lines.append(_fence(stderr_by_name.get(name, "")))
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"