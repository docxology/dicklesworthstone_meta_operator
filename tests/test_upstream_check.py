"""Tests for ``src/upstream_check.py`` — real git, real repos, zero mocks.

Every scenario is manufactured with actual git commands against fixture
repositories built in ``tmp_path``: a bare upstream initialized on ``main``,
a seed clone that pushes the first commit, and per-scenario working clones
mutated with real ``git checkout`` / ``commit`` / ``fetch`` operations.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.models import UpstreamStatus, from_dict
from src.upstream_check import build_report, verify_all, verify_one

GIT_IDENTITY = ["-c", "user.email=test@example.com", "-c", "user.name=Test"]
DEFAULT_BRANCH = "main"


def git(args: list[str], cwd: Path) -> str:
    """Run a real git command and assert success, returning stdout."""
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), text=True, capture_output=True
    )
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc.stdout


def commit_all(repo: Path, message: str) -> str:
    """Stage everything in ``repo`` and create one real commit; return sha."""
    git(["add", "."], repo)
    git([*GIT_IDENTITY, "commit", "-m", message], repo)
    return git(["rev-parse", "HEAD"], repo).strip()


@pytest.fixture
def fleet(tmp_path: Path):
    """Bare upstream on main + factory for fresh working clones."""
    upstream = tmp_path / "upstream.git"
    git(["init", "--bare", "-b", DEFAULT_BRANCH, str(upstream)], tmp_path)
    seed = tmp_path / "seed"
    git(["clone", str(upstream), str(seed)], tmp_path)
    (seed / "README.md").write_text("# fleet\n", encoding="utf-8")
    commit_all(seed, "init")
    git(["push", "origin", DEFAULT_BRANCH], seed)

    def clone(name: str) -> Path:
        dest = tmp_path / name
        git(["clone", str(upstream), str(dest)], tmp_path)
        return dest

    return clone


def test_on_upstream(fleet) -> None:
    work = fleet("work")
    status = verify_one(work, DEFAULT_BRANCH)
    assert status.state == "on_upstream"
    assert status.on_upstream_default is True
    assert status.dirty is False
    assert status.detached is False
    assert status.unborn is False
    assert status.ahead == 0
    assert status.behind == 0
    assert status.checked_out_branch == DEFAULT_BRANCH
    assert status.head_sha == git(["rev-parse", "HEAD"], work).strip()
    assert status.remote_sha == git(
        ["rev-parse", f"origin/{DEFAULT_BRANCH}"], work
    ).strip()


def test_behind_after_upstream_moves(fleet) -> None:
    work = fleet("work")
    other = fleet("other")
    (other / "move.txt").write_text("upstream\n", encoding="utf-8")
    commit_all(other, "upstream moves")
    git(["push", "origin", DEFAULT_BRANCH], other)
    status = verify_one(work, DEFAULT_BRANCH)
    assert status.state == "behind"
    assert status.behind == 1
    assert status.ahead == 0
    assert status.on_upstream_default is False


def test_ahead_with_local_commit(fleet) -> None:
    work = fleet("work")
    (work / "local.txt").write_text("local\n", encoding="utf-8")
    commit_all(work, "local only")
    status = verify_one(work, DEFAULT_BRANCH)
    assert status.state == "ahead"
    assert status.ahead == 1
    assert status.behind == 0
    assert status.on_upstream_default is False


def test_diverged(fleet) -> None:
    work = fleet("work")
    other = fleet("other")
    (work / "local.txt").write_text("local\n", encoding="utf-8")
    commit_all(work, "local only")
    (other / "move.txt").write_text("upstream\n", encoding="utf-8")
    commit_all(other, "upstream moves")
    git(["push", "origin", DEFAULT_BRANCH], other)
    git(["fetch", "origin", DEFAULT_BRANCH, "--quiet"], work)
    status = verify_one(work, DEFAULT_BRANCH)
    (other / "move.txt").write_text("upstream\n", encoding="utf-8")
    assert status.ahead == 1
    assert status.behind == 1
    assert status.state == "diverged"
    assert status.on_upstream_default is False
    assert status.fetched is True


def test_dirty_untracked_file(fleet) -> None:
    work = fleet("work")
    (work / "stray.txt").write_text("untracked\n", encoding="utf-8")
    status = verify_one(work, DEFAULT_BRANCH)
    assert status.state == "dirty"
    assert status.dirty is True
    assert status.checked_out_branch == DEFAULT_BRANCH
    assert status.head_sha != ""
    # Locally origin/main equals HEAD, so alignment is computable even dirty.
    assert status.on_upstream_default is True


def test_dirty_modified_tracked_file_not_on_default(fleet) -> None:
    work = fleet("work")
    (work / "README.md").write_text("modified\n", encoding="utf-8")
    status = verify_one(work, DEFAULT_BRANCH)
    assert status.state == "dirty"
    assert status.dirty is True
    # Branch == default and HEAD == origin/default: alignment is True even dirty.
    assert status.on_upstream_default is True


def test_detached_head(fleet) -> None:
    work = fleet("work")
    git(["checkout", "--detach", "HEAD"], work)
    status = verify_one(work, DEFAULT_BRANCH)
    assert status.state == "detached"
    assert status.detached is True
    assert status.checked_out_branch == ""
    assert status.head_sha == git(["rev-parse", "HEAD"], work).strip()
    assert status.on_upstream_default is False


def test_off_default_branch(fleet) -> None:
    work = fleet("work")
    git(["checkout", "-b", "feature"], work)
    status = verify_one(work, DEFAULT_BRANCH)
    assert status.state == "off_default"
    assert status.checked_out_branch == "feature"
    assert status.on_upstream_default is False
    assert status.head_sha != ""


def test_unborn_empty_repo(tmp_path: Path) -> None:
    empty = tmp_path / "unborn"
    git(["init", "-b", DEFAULT_BRANCH, str(empty)], tmp_path)
    status = verify_one(empty, DEFAULT_BRANCH)
    assert status.state == "unborn"
    assert status.unborn is True
    assert status.head_sha == ""
    assert status.remote_sha == ""
    assert status.ahead == 0
    assert status.behind == 0
    assert status.checked_out_branch == DEFAULT_BRANCH


def test_unborn_clone_of_empty_upstream(tmp_path: Path) -> None:
    empty_bare = tmp_path / "empty.git"
    git(["init", "--bare", "-b", DEFAULT_BRANCH, str(empty_bare)], tmp_path)
    work = tmp_path / "work_unborn"
    proc = subprocess.run(
        ["git", "clone", str(empty_bare), str(work)],
        cwd=str(tmp_path),
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0  # git warns about the empty clone but works
    status = verify_one(work, DEFAULT_BRANCH)
    assert status.state == "unborn"
    assert status.unborn is True


def test_missing_path(tmp_path: Path) -> None:
    status = verify_one(tmp_path / "does_not_exist", DEFAULT_BRANCH)
    assert status.state == "missing"
    assert status.name == "does_not_exist"
    assert status.head_sha == ""
    assert status.on_upstream_default is False


def test_verify_all_sorted_with_missing_and_names(fleet, tmp_path: Path) -> None:
    work = fleet("repo_b")
    git(["checkout", "-b", "feature"], work)
    requests = [
        ("zeta", tmp_path / "nope", DEFAULT_BRANCH),
        ("beta", work, DEFAULT_BRANCH),
        ("alpha", fleet("repo_a"), DEFAULT_BRANCH),
    ]
    statuses = verify_all(requests, fetch_workers=2)
    assert [s.name for s in statuses] == ["alpha", "beta", "zeta"]
    by_name = {s.name: s for s in statuses}
    assert by_name["alpha"].state == "on_upstream"
    assert by_name["beta"].state == "off_default"
    assert by_name["zeta"].state == "missing"
    # verify_all stamps the request name even when it differs from the dir.
    assert by_name["beta"].name == "beta"


def test_verify_all_do_fetch_false_uses_cached_refs(fleet) -> None:
    work = fleet("work")
    other = fleet("other")
    (other / "move.txt").write_text("upstream\n", encoding="utf-8")
    commit_all(other, "upstream moves")
    git(["push", "origin", DEFAULT_BRANCH], other)
    # do_fetch=False the clone reads as on_upstream (stale but offline-safe).
    statuses = verify_all([("stale", work, DEFAULT_BRANCH)], do_fetch=False)
    assert statuses[0].state == "on_upstream"


def test_build_report_ok_count_and_shape(fleet, tmp_path: Path) -> None:
    work = fleet("work")
    statuses = [
        verify_one(work, DEFAULT_BRANCH),  # on_upstream -> ok
        verify_one(tmp_path / "gone", DEFAULT_BRANCH),  # missing -> not ok
        UpstreamStatus(
            name="blank",
            default_branch=DEFAULT_BRANCH,
            checked_out_branch=DEFAULT_BRANCH,
            head_sha="",
            remote_sha="",
            on_upstream_default=False,
            ahead=0,
            behind=0,
            dirty=False,
            detached=False,
            unborn=True,
            state="unborn",  # unborn -> ok
        ),
        UpstreamStatus(
            name="dirty_one",
            default_branch=DEFAULT_BRANCH,
            checked_out_branch=DEFAULT_BRANCH,
            head_sha="abc",
            remote_sha="abc",
            on_upstream_default=True,
            ahead=0,
            behind=0,
            dirty=True,
            detached=False,
            unborn=False,
            state="dirty",  # dirty -> not ok
        ),
    ]
    report = build_report(statuses, generated_at="2026-09-02T00:00:00Z")
    assert report["generated_at"] == "2026-09-02T00:00:00Z"
    assert report["checked"] == 4
    assert report["ok"] == 2
    assert [r["name"] for r in report["repos"]] == [
        "work",
        "gone",
        "blank",
        "dirty_one",
    ]
    assert report["repos"][0]["state"] == "on_upstream"
    # Round-trip: to_dict -> from_dict reconstructs the frozen dataclass.
    rebuilt = from_dict(UpstreamStatus, report["repos"][2])
    assert rebuilt == statuses[2]


def test_build_report_generated_at_defaults(tmp_path: Path) -> None:
    report = build_report(
        [verify_one(tmp_path / "gone", DEFAULT_BRANCH)]
    )
    assert report["checked"] == 1
    assert report["ok"] == 0
    assert report["generated_at"].endswith("Z")
    # The payload must be JSON-serializable end to end.
    json.dumps(report)


def test_stray_directory_maps_to_missing(tmp_path) -> None:
    """A non-git directory verifies as 'missing' instead of aborting the fleet."""
    stray = tmp_path / "stray"
    stray.mkdir()
    (stray / "junk.txt").write_text("not a repo\n", encoding="utf-8")
    status = verify_one(stray, DEFAULT_BRANCH)
    assert status.state == "missing"
    assert status.head_sha == ""


def test_smart_fetch_probes_clean_and_refetches_drifted(tmp_path) -> None:
    """Smart mode: tip-probed clean repo stays unfetched; moved repo is caught.

    Two independent upstreams: `clean` never moves (ls-remote confirms the
    cached ref -> no fetch, still on_upstream); `drifted` moves upstream after
    cloning -> the tip probe differs from the cached ref -> fetched
    re-verification reports `behind`.
    """
    def corpus(tag: str):
        up = tmp_path / f"{tag}.git"
        git(["init", "--bare", "-b", DEFAULT_BRANCH, str(up)], tmp_path)
        seed = tmp_path / f"{tag}_seed"
        git(["clone", str(up), str(seed)], tmp_path)
        (seed / "r.md").write_text(f"# {tag}\n", encoding="utf-8")
        commit_all(seed, "init")
        git(["push", "origin", DEFAULT_BRANCH], seed)
        work = tmp_path / f"{tag}_work"
        git(["clone", str(up), str(work)], tmp_path)
        return seed, work

    _seed_a, clean = corpus("alpha")
    seed_b, drifted = corpus("beta")
    (seed_b / "new.txt").write_text("upstream moves\n", encoding="utf-8")
    commit_all(seed_b, "upstream moves")
    git(["push", "origin", DEFAULT_BRANCH], seed_b)

    requests = [("clean", clean, DEFAULT_BRANCH), ("drifted", drifted, DEFAULT_BRANCH)]
    statuses = {s.name: s for s in verify_all(requests, smart_fetch=True)}
    assert statuses["clean"].state == "on_upstream"
    assert statuses["clean"].fetched is False
    assert statuses["drifted"].state == "behind"
    assert statuses["drifted"].fetched is True
    assert statuses["drifted"].behind == 1
