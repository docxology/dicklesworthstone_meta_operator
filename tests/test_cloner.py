"""Tests for ``src/cloner.py`` — real git, real fixture repos, zero mocks.

Fixture repos are genuine bare repositories created with ``git init --bare``
plus one commit pushed from a temporary work clone. Everything runs offline
against local filesystem remotes only.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.cloner import MISMATCH_ERROR, clone_corpus, execute_plan, plan_clones
from src.models import CloneOutcome, ClonePlanEntry, from_dict, to_dict

GIT_IDENTITY = ["-c", "user.email=operator@example.com", "-c", "user.name=Operator"]


def _run(argv: list[str], cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def origin_dir(tmp_path: Path) -> Path:
    path = tmp_path / "origin"
    path.mkdir()
    return path


def _make_bare_repo(origin_dir: Path, name: str) -> Path:
    """Create a real bare fixture repo with one commit on ``main``."""
    bare = origin_dir / f"{name}.git"
    _run(["git", "init", "--bare", "-b", "main", "-q", str(bare)])
    work = origin_dir / f"{name}-work"
    _run(["git", "clone", "-q", str(bare), str(work)])
    (work / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    _run(["git", "add", "README.md"], cwd=work)
    _run(["git"] + GIT_IDENTITY + ["commit", "-q", "-m", f"init {name}"], cwd=work)
    _run(["git", "push", "-q", "origin", "main"], cwd=work)
    return bare


def test_plan_clones_classifies_and_sorts(tmp_path: Path, origin_dir: Path):
    bare = _make_bare_repo(origin_dir, "zeta")
    repos_dir = tmp_path / "repos"
    existing = repos_dir / "beta"
    _run(["git", "clone", "-q", str(bare), str(existing)])
    stray = repos_dir / "stray"
    stray.mkdir()
    (stray / "junk.txt").write_text("not a repo", encoding="utf-8")

    entries = [
        ("stray", "https://example.com/stray.git"),
        ("zeta", "https://example.com/zeta.git"),
        ("beta", "https://example.com/beta.git"),
        ("gamma", "https://example.com/gamma.git"),
    ]
    plan = plan_clones(entries, repos_dir)

    assert [e.name for e in plan] == ["beta", "gamma", "stray", "zeta"]
    by_name = {e.name: e for e in plan}
    assert (by_name["beta"].needed, by_name["beta"].reason) == (False, "exists_ok")
    assert (by_name["gamma"].needed, by_name["gamma"].reason) == (True, "missing")
    assert (by_name["stray"].needed, by_name["stray"].reason) == (True, "exists_mismatch")
    assert (by_name["zeta"].needed, by_name["zeta"].reason) == (True, "missing")
    assert by_name["gamma"].dest == str(repos_dir / "gamma")
    assert by_name["gamma"].clone_url == "https://example.com/gamma.git"


def test_plan_clones_is_pure(tmp_path: Path):
    repos_dir = tmp_path / "repos"
    plan = plan_clones([("alpha", "https://example.com/alpha.git")], repos_dir)
    assert len(plan) == 1
    assert plan[0].reason == "missing"
    assert not repos_dir.exists()  # planning must not create anything


def test_execute_plan_clones_real_repos_then_idempotent(tmp_path: Path, origin_dir: Path):
    alpha = _make_bare_repo(origin_dir, "alpha")
    gamma = _make_bare_repo(origin_dir, "gamma")
    repos_dir = tmp_path / "repos"

    plan = plan_clones([("gamma", str(gamma)), ("alpha", str(alpha))], repos_dir)
    first = execute_plan(plan, workers=2)
    assert [o.name for o in first] == ["alpha", "gamma"]
    for outcome in first:
        assert outcome.status == "cloned"
        assert outcome.error is None
        assert outcome.seconds > 0.0
        assert (Path(outcome.dest) / ".git").is_dir()

    second = execute_plan(plan_clones([("gamma", str(gamma)), ("alpha", str(alpha))], repos_dir))
    assert [o.status for o in second] == ["already_cloned", "already_cloned"]
    assert all(o.seconds == 0.0 for o in second)


def test_execute_plan_mismatch_never_clones_over(tmp_path: Path, origin_dir: Path):
    bare = _make_bare_repo(origin_dir, "target")
    repos_dir = tmp_path / "repos"
    dest = repos_dir / "target"
    dest.mkdir(parents=True)
    (dest / "important.txt").write_text("keep me", encoding="utf-8")

    plan = plan_clones([("target", str(bare))], repos_dir)
    (outcome,) = execute_plan(plan)
    assert outcome.status == "mismatch"
    assert outcome.error == MISMATCH_ERROR
    assert (dest / "important.txt").read_text(encoding="utf-8") == "keep me"
    assert not (dest / ".git").exists()  # nothing was cloned over the stray dir


def test_execute_plan_reports_failed_clone(tmp_path: Path):
    repos_dir = tmp_path / "repos"
    missing_url = str(tmp_path / "no_such_repo")
    plan = plan_clones([("ghost", missing_url)], repos_dir)
    (outcome,) = execute_plan(plan)
    assert outcome.status == "failed"
    assert outcome.error  # git's stderr made it into the outcome
    assert len(outcome.error) <= 400
    assert not (repos_dir / "ghost" / ".git").exists()


def test_execute_plan_runner_seam_returns_and_raises(tmp_path: Path, origin_dir: Path):
    bare = _make_bare_repo(origin_dir, "seam")
    repos_dir = tmp_path / "repos"
    plan = plan_clones([("seam", str(bare))], repos_dir)

    def failing_runner(_argv):
        return 128, "fatal: simulated git failure"

    (outcome,) = execute_plan(plan, runner=failing_runner)
    assert outcome.status == "failed"
    assert outcome.error == "fatal: simulated git failure"

    def exploding_runner(_argv):
        raise RuntimeError("runner exploded")

    (outcome,) = execute_plan(plan, runner=exploding_runner)
    assert outcome.status == "failed"
    assert "runner exploded" in outcome.error
    assert not (repos_dir / "seam" / ".git").exists()


def test_execute_plan_never_raises_and_sorts(tmp_path: Path, origin_dir: Path):
    """A crashing runner across every entry still yields sorted failed outcomes."""
    repos_dir = tmp_path / "repos"
    plan = plan_clones(
        [("b_repo", "https://example.com/b.git"), ("a_repo", "https://example.com/a.git")],
        repos_dir,
    )

    def always_raises(_argv):
        raise OSError("no git anywhere")

    outcomes = execute_plan(plan, workers=4, runner=always_raises)
    assert [o.name for o in outcomes] == ["a_repo", "b_repo"]
    assert all(o.status == "failed" for o in outcomes)


def test_clone_corpus_builds_repos_dir_and_is_idempotent(tmp_path: Path, origin_dir: Path):
    alpha = _make_bare_repo(origin_dir, "alpha")
    gamma = _make_bare_repo(origin_dir, "gamma")
    project_root = tmp_path / "project"
    project_root.mkdir()

    registry = {
        "generated_at": "2026-09-02T00:00:00Z",
        "github_user": "Dicklesworthstone",
        "include_forks": False,
        "repos": [
            _registry_entry(raw)
            for raw in [
                {"name": "gamma", "clone_url": str(gamma)},
                {"name": "alpha", "clone_url": str(alpha)},
            ]
        ],
    }

    first = clone_corpus(registry, project_root, workers=2)
    assert [o.name for o in first] == ["alpha", "gamma"]
    assert all(o.status == "cloned" for o in first)
    assert (project_root / "repos" / "alpha" / ".git").is_dir()  # default repos_dir

    second = clone_corpus(registry, project_root)
    assert all(o.status == "already_cloned" for o in second)


def _registry_entry(raw: dict) -> dict:
    """Minimal RepoMeta.to_dict shape for registry fixtures."""
    return {
        "name": raw["name"],
        "html_url": f"https://github.com/x/{raw['name']}",
        "clone_url": raw["clone_url"],
        "default_branch": "main",
        "language": "",
        "description": "",
        "size_kb": 0,
        "pushed_at": "",
        "fork": False,
        "archived": False,
        "topics": [],
    }


def test_clone_corpus_tolerates_raw_repmeta_entries(tmp_path: Path, origin_dir: Path):
    from src.models import RepoMeta

    bare = _make_bare_repo(origin_dir, "raw_meta")
    project_root = tmp_path / "project"
    registry = {
        "repos": [
            RepoMeta(
                name="raw_meta",
                html_url="https://github.com/x/raw_meta",
                clone_url=str(bare),
                default_branch="main",
                language="",
                description="",
                size_kb=0,
                pushed_at="",
                fork=False,
                archived=False,
                topics=[],
            )
        ]
    }
    (outcome,) = clone_corpus(registry, project_root)
    assert outcome.status == "cloned"


def test_clone_outcome_roundtrip_via_from_dict():
    outcome = CloneOutcome(
        name="alpha", status="cloned", dest="/repos/alpha", error=None, seconds=1.25
    )
    restored = from_dict(CloneOutcome, to_dict(outcome))
    assert restored == outcome
    failed = CloneOutcome(name="beta", status="failed", dest="/repos/beta", error="boom")
    assert from_dict(CloneOutcome, to_dict(failed)) == failed


def test_clone_plan_entry_roundtrip_via_from_dict():
    entry = ClonePlanEntry(
        name="alpha", clone_url="https://example.com/a.git", dest="/repos/alpha",
        needed=True, reason="missing",
    )
    assert from_dict(ClonePlanEntry, to_dict(entry)) == entry