"""Upstream verification: is every local clone on its upstream default branch?

Implements the "confirm we are on all upstream mains" directive. For each repo
path, determines one of the states in ``UPSTREAM_STATES`` by real ``git``
subprocess inspection (no mocks, no network beyond ``git fetch`` itself):

1. ``unborn``  — repository exists but HEAD points at a branch with no commits
   (the shape of an empty upstream that was cloned).
2. ``detached`` — HEAD is not a symbolic ref (detached checkout).
3. ``dirty``   — worktree has uncommitted/untracked changes (porcelain output
   non-empty). Branch/sha info is still reported; ``on_upstream_default`` is
   computed from the locally-known ``origin/<default>`` when both resolve.
4. Otherwise the ``origin/<default>`` ref is refreshed by ``git fetch`` (when
   allowed) and ahead/behind counts decide ``on_upstream`` / ``ahead`` /
   ``behind`` / ``diverged``; a branch other than the default is
   ``off_default``.

Edge case (deliberate): when the checked-out branch equals the default but
``origin/<default>`` cannot be resolved (including after a successful fetch),
the state is ``missing`` — documented as "upstream default ref not found",
because a deleted upstream default is indistinguishable from an unreachable
one locally and both mean "we cannot confirm we are on upstream main".

Unexpected git failures raise ``RuntimeError`` with context; only the
enumerated conditions above map to states. A non-existent path maps to
``missing`` in :func:`verify_all` (the caller never has to pre-check).
"""

from __future__ import annotations

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from src.models import UPSTREAM_OK_STATES, UpstreamStatus, to_dict

logger = logging.getLogger(__name__)

__all__ = ["_run_git", "verify_one", "verify_all", "build_report"]




def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one ``git`` command in ``cwd`` with text-mode captured output."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
    )


def _resolve_head(repo: Path) -> tuple[bool, bool, str, str]:
    """Inspect HEAD: (rev_ok, symbolic_ok, sha, checked_out_branch).

    ``rev_ok``  — ``git rev-parse --verify -q HEAD`` succeeded.
    ``sym_ok``  — ``git symbolic-ref -q HEAD`` succeeded (HEAD is a branch).
    ``sha``     — commit sha when ``rev_ok``, else "".
    ``branch``  — short symbolic-ref name when ``sym_ok``, else "".
    """
    rev = _run_git(["rev-parse", "--verify", "-q", "HEAD"], repo)
    sym = _run_git(["symbolic-ref", "-q", "--short", "HEAD"], repo)
    rev_ok = rev.returncode == 0
    sym_ok = sym.returncode == 0
    return rev_ok, sym_ok, (rev.stdout.strip() if rev_ok else ""), (
        sym.stdout.strip() if sym_ok else ""
    )


def _resolve_remote(repo: Path, default_branch: str) -> str:
    """Resolve ``origin/<default_branch>`` to a sha, or "" when unresolvable."""
    proc = _run_git(["rev-parse", "--verify", "-q", f"origin/{default_branch}"], repo)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _is_dirty(repo: Path) -> bool:
    """True when the worktree has any uncommitted or untracked changes."""
    proc = _run_git(["status", "--porcelain"], repo)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git status --porcelain failed in {repo}: rc={proc.returncode} "
            f"stderr={proc.stderr.strip()!r}"
        )
    return bool(proc.stdout.strip())


def _verify_existing(repo: Path, default_branch: str, *, do_fetch: bool) -> UpstreamStatus:
    """Verify one repo whose path exists (unborn/detached/dirty/fetch path)."""
    rev_ok, sym_ok, sha, branch = _resolve_head(repo)
    if not _run_git(["rev-parse", "--git-dir"], repo).stdout.strip():
        # A stray directory (not a git repository — e.g. a failed clone left
        # behind): classify as missing instead of aborting the fleet report.
        return UpstreamStatus(
            name=repo.name,
            default_branch=default_branch,
            checked_out_branch="",
            head_sha="",
            remote_sha="",
            on_upstream_default=False,
            ahead=0,
            behind=0,
            dirty=False,
            detached=False,
            unborn=False,
            state="missing",
        )

    # 1. unborn: no commit at HEAD, but HEAD is a symbolic ref (fresh clone of
    # an empty upstream).
    if not rev_ok and sym_ok:
        return UpstreamStatus(
            name=repo.name,
            default_branch=default_branch,
            checked_out_branch=branch,
            head_sha="",
            remote_sha="",
            on_upstream_default=False,
            ahead=0,
            behind=0,
            dirty=_is_dirty(repo),
            detached=False,
            unborn=True,
            state="unborn",
        )

    # 2. detached: HEAD is not a symbolic ref.
    if not sym_ok:
        return UpstreamStatus(
            name=repo.name,
            default_branch=default_branch,
            checked_out_branch="",
            head_sha=sha,
            remote_sha="",
            on_upstream_default=False,
            ahead=0,
            behind=0,
            dirty=_is_dirty(repo),
            detached=True,
            unborn=False,
            state="detached",
        )

    # 3. dirty: uncommitted/untracked changes shadow branch alignment.
    dirty = _is_dirty(repo)
    if dirty:
        remote_sha = _resolve_remote(repo, default_branch)
        on_default = bool(
            rev_ok and remote_sha and sha == remote_sha and branch == default_branch
        )
        return UpstreamStatus(
            name=repo.name,
            default_branch=default_branch,
            checked_out_branch=branch,
            head_sha=sha,
            remote_sha=remote_sha,
            on_upstream_default=on_default,
            ahead=0,
            behind=0,
            dirty=True,
            detached=False,
            unborn=False,
            state="dirty",
        )

    # 4. fetch: refresh origin/<default>; a failed fetch is tolerated (the
    # locally cached remote ref still says something) but recorded.
    fetched = False
    if do_fetch:
        fetch = _run_git(["fetch", "origin", default_branch, "--quiet"], repo)
        fetched = fetch.returncode == 0
        if not fetched:
            logger.warning(
                "git fetch origin %s failed in %s: %s",
                default_branch,
                repo,
                fetch.stderr.strip(),
            )
    remote_sha = _resolve_remote(repo, default_branch)

    # 5./6./7. branch alignment and ahead/behind accounting.
    if branch != default_branch:
        return UpstreamStatus(
            name=repo.name,
            default_branch=default_branch,
            checked_out_branch=branch,
            head_sha=sha,
            remote_sha=remote_sha,
            on_upstream_default=False,
            ahead=0,
            behind=0,
            dirty=False,
            detached=False,
            unborn=False,
            state="off_default",
            fetched=fetched,
        )

    if not remote_sha:
        # Branch == default but origin/<default> is unresolvable even after a
        # (possibly successful) fetch: the upstream default ref was not found.
        return UpstreamStatus(
            name=repo.name,
            default_branch=default_branch,
            checked_out_branch=branch,
            head_sha=sha,
            remote_sha="",
            on_upstream_default=False,
            ahead=0,
            behind=0,
            dirty=False,
            detached=False,
            unborn=False,
            state="missing",
            fetched=fetched,
        )

    counts = _run_git(
        ["rev-list", "--left-right", "--count", f"HEAD...origin/{default_branch}"],
        repo,
    )
    if counts.returncode != 0:
        raise RuntimeError(
            f"git rev-list --left-right --count failed in {repo}: "
            f"rc={counts.returncode} stderr={counts.stderr.strip()!r}"
        )
    ahead_s, behind_s = counts.stdout.split()
    ahead, behind = int(ahead_s), int(behind_s)
    if ahead > 0 and behind > 0:
        state = "diverged"
    elif behind > 0:
        state = "behind"
    elif ahead > 0:
        state = "ahead"
    else:
        state = "on_upstream"
    return UpstreamStatus(
        name=repo.name,
        default_branch=default_branch,
        checked_out_branch=branch,
        head_sha=sha,
        remote_sha=remote_sha,
        on_upstream_default=(state == "on_upstream"),
        ahead=ahead,
        behind=behind,
        dirty=False,
        detached=False,
        unborn=False,
        state=state,
        fetched=fetched,
    )

def _remote_tip_moved(repo: Path, default_branch: str) -> bool:
    """True when ``origin``'s current tip for ``default_branch`` differs from
    the locally cached ``origin/<default_branch>`` ref (cheap ``ls-remote``,
    no object transfer). Unresolvable tips (empty upstream, offline) count as
    NOT moved — the offline classification stands."""
    probe = _run_git(
        ["ls-remote", "origin", f"refs/heads/{default_branch}"], repo
    )
    if probe.returncode != 0:
        logger.warning(
            "git ls-remote origin %s failed in %s: %s",
            default_branch,
            repo,
            probe.stderr.strip(),
        )
        return False
    remote_tip = probe.stdout.split()[0] if probe.stdout.split() else ""
    if not remote_tip:
        return False
    cached = _resolve_remote(repo, default_branch)
    return bool(cached) and remote_tip != cached

def verify_one(repo_path: Path, default_branch: str, *, do_fetch: bool = True) -> UpstreamStatus:
    """Verify one local clone against its upstream default branch.

    Never inspects the network directly — only ``git`` does. Raises
    ``RuntimeError`` on unexpected git failures; the caller is responsible for
    existence of ``repo_path`` (see :func:`verify_all` for the batch shape).
    """
    if not repo_path.is_dir():
        return UpstreamStatus(
            name=repo_path.name,
            default_branch=default_branch,
            checked_out_branch="",
            head_sha="",
            remote_sha="",
            on_upstream_default=False,
            ahead=0,
            behind=0,
            dirty=False,
            detached=False,
            unborn=False,
            state="missing",
        )
    return _verify_existing(repo_path, default_branch, do_fetch=do_fetch)


def verify_all(
    requests: list[tuple[str, Path, str]],
    *,
    do_fetch: bool = True,
    fetch_workers: int = 8,
    smart_fetch: bool = False,
) -> list[UpstreamStatus]:
    """Verify many (name, repo_path, default_branch) requests, sorted by name.

    Missing paths map to the ``missing`` state without touching git. When
    ``do_fetch`` is true the per-repo verification (including its fetch) runs
    in a ``ThreadPoolExecutor(max_workers=fetch_workers)``; otherwise each
    repo is verified sequentially with ``do_fetch=False`` (cached remote refs
    only, fully offline).

    With ``smart_fetch`` (and ``do_fetch``), a first offline pass over cached
    refs classifies every clone. Repos not cleanly on their upstream get a
    fetched re-verification; clean repos get a cheap ``git ls-remote`` tip
    probe — if the remote tip moved past the cached ref, they are fetched and
    re-verified too. A synced corpus thus costs only lightweight network
    probes instead of full fetches, while still detecting upstream movement.
    """
    results: dict[str, UpstreamStatus] = {}
    existing: list[tuple[str, Path, str]] = []
    for name, repo_path, default_branch in requests:
        if not repo_path.is_dir():
            results[name] = UpstreamStatus(
                name=name,
                default_branch=default_branch,
                checked_out_branch="",
                head_sha="",
                remote_sha="",
                on_upstream_default=False,
                ahead=0,
                behind=0,
                dirty=False,
                detached=False,
                unborn=False,
                state="missing",
            )
        else:
            existing.append((name, repo_path, default_branch))

    fetch_targets = existing
    if do_fetch and smart_fetch:
        for name, repo, branch in existing:
            results[name] = replace(
                _verify_existing(repo, branch, do_fetch=False), name=name
            )
        stale_names = {
            name
            for name, repo, branch in existing
            if results[name].state not in UPSTREAM_OK_STATES
        }
        tip_targets = [
            (name, repo, branch)
            for name, repo, branch in existing
            if results[name].state in UPSTREAM_OK_STATES
        ]
        with ThreadPoolExecutor(max_workers=max(1, fetch_workers)) as probe_pool:
            probes = [
                (name, probe_pool.submit(_remote_tip_moved, repo, branch))
                for name, repo, branch in tip_targets
            ]
            for name, future in probes:
                if future.result():
                    stale_names.add(name)
        fetch_targets = [
            (name, repo, branch)
            for name, repo, branch in existing
            if name in stale_names
        ]

    if do_fetch:
        with ThreadPoolExecutor(max_workers=max(1, fetch_workers)) as pool:
            futures = [
                (name, pool.submit(_verify_existing, repo, branch, do_fetch=True))
                for name, repo, branch in fetch_targets
            ]
            for name, future in futures:
                results[name] = replace(future.result(), name=name)
    else:
        for name, repo, branch in existing:
            results[name] = replace(
                _verify_existing(repo, branch, do_fetch=False), name=name
            )

    return [results[name] for name in sorted(results)]


def build_report(
    statuses: list[UpstreamStatus], *, generated_at: str | None = None
) -> dict:
    """Assemble the ``upstream_status.json`` artifact payload (exact shape)."""
    if generated_at is None:
        from datetime import datetime, timezone

        generated_at = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    ok = sum(1 for s in statuses if s.state in UPSTREAM_OK_STATES)
    return {
        "generated_at": generated_at,
        "checked": len(statuses),
        "ok": ok,
        "repos": [to_dict(s) for s in statuses],
    }
