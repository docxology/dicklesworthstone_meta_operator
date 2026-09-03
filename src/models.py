"""Typed models shared across the meta-operator.

Pure dataclasses only: no I/O, no subprocess, no imports beyond the standard
library. Every cross-module contract — registry entries, clone outcomes,
upstream states, inventory profiles, orchestration runs, gate checks — is
expressed here. JSON artifacts store ``to_dict()`` shapes; loaders reconstruct
via :func:`from_dict`.

State vocabularies (stable string literals consumed by the dashboard and gate):

``CloneOutcome.status``
    ``cloned`` | ``already_cloned`` | ``failed`` | ``mismatch``

``UpstreamStatus.state``
    ``on_upstream``   — HEAD == origin/<default_branch>, clean worktree
    ``behind``        — strictly behind upstream default (fast-forwardable)
    ``ahead``         — strictly ahead of upstream default
    ``diverged``      — both ahead and behind
    ``dirty``         — uncommitted changes in the worktree
    ``detached``      — detached HEAD
    ``unborn``        — repository has no commits (upstream is empty)
    ``off_default``   — clean worktree, but on a non-default branch
    ``missing``       — no local clone found (or path is not a git repository)
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any

# ---------------------------------------------------------------------------
# State vocabularies
# ---------------------------------------------------------------------------

CLONE_STATUSES: frozenset[str] = frozenset(
    {"cloned", "already_cloned", "failed", "mismatch"}
)

# Clone statuses that count as "this repo needs operator attention".
CLONE_FAILED_STATUSES: frozenset[str] = frozenset({"failed", "mismatch"})

UPSTREAM_STATES: frozenset[str] = frozenset(
    {
        "on_upstream",
        "behind",
        "ahead",
        "diverged",
        "dirty",
        "detached",
        "off_default",
        "unborn",
        "missing",
    }
)

# States that count as "in sync with upstream" for the health gate.
# ``unborn`` passes: an empty upstream has nothing to be behind.
UPSTREAM_OK_STATES: frozenset[str] = frozenset({"on_upstream", "unborn"})

AUTO_COMMAND_KEYS: frozenset[str] = frozenset({"test", "lint", "typecheck"})


# ---------------------------------------------------------------------------
# Serialization helpers (recursive, dataclass-aware)
# ---------------------------------------------------------------------------


def to_dict(obj: Any) -> Any:
    """Convert dataclasses / lists / dicts recursively to JSON-ready shapes."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_dict(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): to_dict(v) for k, v in obj.items()}
    return obj


def from_dict(cls: type, raw: dict[str, Any]) -> Any:
    """Reconstruct a dataclass from its ``to_dict`` shape (shallow).

    Nested dataclasses (e.g. ``GateReport.checks``) are NOT auto-resolved;
    owning modules reconstruct them explicitly.
    """
    if not isinstance(raw, dict):
        raise TypeError(f"{cls.__name__} expects a dict, got {type(raw).__name__}")
    kwargs: dict[str, Any] = {f.name: raw[f.name] for f in fields(cls) if f.name in raw}
    missing = [
        f.name
        for f in fields(cls)
        if f.name not in kwargs
        and f.default is dataclasses.MISSING
        and f.default_factory is dataclasses.MISSING
    ]
    if missing:
        raise ValueError(f"{cls.__name__} missing required fields: {missing}")
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# Registry layer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepoMeta:
    """One GitHub repository as reported by the GitHub API."""

    name: str
    html_url: str
    clone_url: str
    default_branch: str
    language: str
    description: str
    size_kb: int
    pushed_at: str
    fork: bool
    archived: bool
    topics: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Clone layer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClonePlanEntry:
    """Plan row produced by cloner.plan_clones (pure)."""

    name: str
    clone_url: str
    dest: str  # absolute path as string (paths are not pure-portable in JSON)
    needed: bool
    reason: str  # missing | exists_ok | exists_mismatch


@dataclass(frozen=True)
class CloneOutcome:
    """Result of one clone execution."""

    name: str
    status: str  # CLONE_STATUSES
    dest: str
    error: str | None = None
    seconds: float = 0.0


# ---------------------------------------------------------------------------
# Upstream verification layer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UpstreamStatus:
    """Verification state of one local clone against its upstream default."""

    name: str
    default_branch: str
    checked_out_branch: str
    head_sha: str
    remote_sha: str
    on_upstream_default: bool
    ahead: int
    behind: int
    dirty: bool
    detached: bool
    unborn: bool
    state: str  # UPSTREAM_STATES
    # True when origin/<default> was freshly fetched during THIS verification;
    # False for pre-fetch exit paths, --no-fetch mode, and failed fetches.
    fetched: bool = False


# ---------------------------------------------------------------------------
# Inventory layer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepoProfile:
    """Interpretability profile for one cloned repo."""

    name: str
    primary_language: str
    languages: dict[str, int]  # extension (with dot, lowercase) -> line count
    total_loc: int
    file_count: int
    readme_title: str
    readme_summary: str
    manifests: dict[str, str]  # manifest filename -> path relative to repo root
    entry_points: list[str]
    has_tests: bool
    test_cmd: str | None
    auto_cmds: dict[str, str]  # test | lint | typecheck -> command
    last_commit_sha: str
    last_commit_date: str
    last_commit_message: str


# ---------------------------------------------------------------------------
# Orchestration layer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunResult:
    """Result of running one command in one repo."""

    name: str
    command: str
    exit_code: int | None  # None when timed out or skipped
    timed_out: bool
    skipped: bool
    skip_reason: str
    seconds: float
    stdout_tail: str
    stderr_tail: str


# ---------------------------------------------------------------------------
# Health gate layer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateCheck:
    """One binary check emitted by the health gate."""

    check_id: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class GateReport:
    """Aggregate gate result: passed iff every check passed."""

    checks: list[GateCheck]
    generated_at: str

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)
