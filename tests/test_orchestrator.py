"""Tests for the orchestration layer (src/orchestrator.py).

Offline and zero-mock: fake repos are real directories under ``tmp_path``; the
default runner path exercises real ``subprocess`` calls against ``sys.executable``;
one test injects a plain Python function as the runner seam (no mocking library).
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pytest

from src.models import RunResult, from_dict, to_dict
from src.orchestrator import (
    SelectorSpec,
    execute_runs,
    filter_repos,
    resolve_auto,
    plan_runs,
    render_run_report,
    run_and_save,
    summarize,
)

PY = sys.executable


def make_repo(root: Path, name: str, *, with_git: bool = True) -> Path:
    """Create a fake repo directory with (or without) a ``.git`` marker."""
    repo = root / name
    repo.mkdir(parents=True, exist_ok=True)
    if with_git:
        (repo / ".git").mkdir(exist_ok=True)
    return repo


def fake_runner(name: str, cmd: str, repo_path: Path) -> RunResult:
    """Injected runner: records the call and returns a fixed success result."""
    return RunResult(
        name=name,
        command=cmd,
        exit_code=0,
        timed_out=False,
        skipped=False,
        skip_reason="",
        seconds=0.01,
        stdout_tail=f"injected:{repo_path.name}",
        stderr_tail="",
    )


# ---------------------------------------------------------------------------
# SelectorSpec validation
# ---------------------------------------------------------------------------


def test_selector_spec_accepts_valid_sorts() -> None:
    for sort in ("name", "size", "loc", "recent"):
        spec = SelectorSpec(sort=sort)
        assert spec.sort == sort


def test_selector_spec_rejects_invalid_sort() -> None:
    with pytest.raises(ValueError, match="sort"):
        SelectorSpec(sort="bogus")


# ---------------------------------------------------------------------------
# filter_repos — pure, table-driven over every filter/sort/limit branch
# ---------------------------------------------------------------------------


PROFILES: dict[str, dict] = {
    "alpha": {
        "name": "alpha",
        "primary_language": "Python",
        "total_loc": 500,
        "size_kb": 1200,
        "last_commit_date": "2026-01-05",
    },
    "beta": {
        "name": "beta",
        "primary_language": "Rust",
        "total_loc": 9000,
        "size_kb": 300,
        "last_commit_date": "2026-03-01",
    },
    "gamma": {
        "name": "gamma",
        "primary_language": "Python",
        "total_loc": 8000,
        "size_kb": 300,
        "last_commit_date": "2026-02-01",
    },
    "delta": {
        "name": "delta",
        "primary_language": "Go",
        "total_loc": 100,
        "size_kb": 5000,
        "last_commit_date": "2025-01-01",
    },
}

FILTER_CASES = [
    ("no filters, name sort", SelectorSpec(), ["alpha", "beta", "delta", "gamma"]),
    (
        "set membership",
        SelectorSpec(set_=("beta", "gamma", "nonexistent")),
        ["beta", "gamma"],
    ),
    (
        "language filter",
        SelectorSpec(language="Python"),
        ["alpha", "gamma"],
    ),
    (
        "min_loc filter",
        SelectorSpec(min_loc=1000),
        ["beta", "gamma"],
    ),
    (
        "exclude filter",
        SelectorSpec(exclude=("beta", "delta")),
        ["alpha", "gamma"],
    ),
    ("limit after sort", SelectorSpec(limit=2), ["alpha", "beta"]),
    (
        "size sort desc with name tiebreak",
        SelectorSpec(sort="size"),
        ["delta", "alpha", "beta", "gamma"],
    ),
    (
        "loc sort desc",
        SelectorSpec(sort="loc"),
        ["beta", "gamma", "alpha", "delta"],
    ),
    (
        "recent sort desc",
        SelectorSpec(sort="recent"),
        ["beta", "gamma", "alpha", "delta"],
    ),
    (
        "loc sort desc with limit",
        SelectorSpec(sort="loc", limit=2),
        ["beta", "gamma"],
    ),
    (
        "combined: set + language + min_loc + exclude + limit",
        SelectorSpec(
            set_=("alpha", "beta", "gamma"),
            language="Python",
            min_loc=400,
            exclude=("gamma",),
        ),
        ["alpha"],
    ),
]

@pytest.mark.parametrize(
    ("label", "spec", "expected"), FILTER_CASES, ids=[c[0] for c in FILTER_CASES]
)
def test_filter_repos_branches(label: str, spec: SelectorSpec, expected: list[str]) -> None:
    assert filter_repos(PROFILES, spec) == expected, label


def test_filter_repos_is_pure() -> None:
    import copy

    profiles = copy.deepcopy(PROFILES)
    filter_repos(profiles, SelectorSpec(sort="size", limit=1))
    assert profiles == PROFILES


def test_filter_repos_accepts_extra_keys() -> None:
    profiles = {name: {**p, "readme_title": f"{name} readme"} for name, p in PROFILES.items()}
    assert filter_repos(profiles, SelectorSpec(language="Go")) == ["delta"]


# ---------------------------------------------------------------------------
# plan_runs
# ---------------------------------------------------------------------------


def test_plan_runs_sorted_with_identical_command() -> None:
    assert plan_runs(["zeta", "alpha"], "pytest -q") == [
        ("alpha", "pytest -q"),
        ("zeta", "pytest -q"),
    ]


# ---------------------------------------------------------------------------
# execute_runs — real subprocess against fake repos
# ---------------------------------------------------------------------------


def test_execute_success(tmp_path: Path) -> None:
    make_repo(tmp_path, "ok_repo")
    results = execute_runs([("ok_repo", f'{PY} -c "print(\'hello\')"')], tmp_path)
    assert len(results) == 1
    r = results[0]
    assert r.exit_code == 0
    assert not r.timed_out and not r.skipped
    assert "hello" in r.stdout_tail
    assert r.stderr_tail == ""
    assert r.seconds > 0.0


def test_execute_failing_command(tmp_path: Path) -> None:
    make_repo(tmp_path, "bad_repo")
    results = execute_runs(
        [("bad_repo", f'{PY} -c "import sys; sys.exit(3)"')], tmp_path
    )
    r = results[0]
    assert r.exit_code == 3
    assert not r.timed_out and not r.skipped


def test_execute_timeout(tmp_path: Path) -> None:
    make_repo(tmp_path, "slow_repo")
    started = time.monotonic()
    results = execute_runs(
        [("slow_repo", f'{PY} -c "import time; time.sleep(3)"')], tmp_path, timeout_s=1
    )
    r = results[0]
    assert r.exit_code is None
    assert r.timed_out
    assert 0.9 <= time.monotonic() - started < 2.5


def test_execute_missing_clone_skipped(tmp_path: Path) -> None:
    make_repo(tmp_path, "no_git", with_git=False)
    results = execute_runs([("no_git", "echo hi")], tmp_path)
    r = results[0]
    assert r.skipped and r.skip_reason == "missing clone"
    assert r.exit_code is None and r.seconds == 0.0
    assert r.stdout_tail == "" and r.stderr_tail == ""


def test_tail_truncation(tmp_path: Path) -> None:
    make_repo(tmp_path, "noisy")
    tail_bytes = 1000
    results = execute_runs(
        [("noisy", f'{PY} -c "print(50000 * \'x\'); print(\'THE_END\')"')],
        tmp_path,
        tail_bytes=tail_bytes,
    )
    tail = results[0].stdout_tail
    assert len(tail) <= tail_bytes
    assert tail.rstrip().endswith("THE_END")


def test_runner_returned_tails_pass_through(tmp_path: Path) -> None:
    make_repo(tmp_path, "byteme")
    results = execute_runs(
        [("byteme", "x")],
        tmp_path,
        runner=lambda name, cmd, path: RunResult(
            name=name, command=cmd, exit_code=0, timed_out=False, skipped=False,
            skip_reason="", seconds=0.0,
            stdout_tail="a" * 50, stderr_tail="b" * 50,
        ),
    )
    assert results[0].stdout_tail == "a" * 50
    assert results[0].stderr_tail == "b" * 50


def test_overrides_swap_command_per_repo(tmp_path: Path) -> None:
    for name in ("aaa", "bbb"):
        make_repo(tmp_path, name)
    plan = plan_runs(["aaa", "bbb"], "echo plan_cmd")
    results = execute_runs(
        plan,
        tmp_path,
        overrides={"aaa": f'{PY} -c "import sys; sys.exit(7)"'},
    )
    by_name = {r.name: r for r in results}
    assert by_name["aaa"].command == f'{PY} -c "import sys; sys.exit(7)"'
    assert by_name["aaa"].exit_code == 7
    assert by_name["bbb"].command == "echo plan_cmd"
    assert by_name["bbb"].exit_code == 0


def test_runner_injection(tmp_path: Path) -> None:
    make_repo(tmp_path, "injected")
    results = execute_runs([("injected", "anything")], tmp_path, runner=fake_runner)
    r = results[0]
    assert r.exit_code == 0
    assert r.stdout_tail == "injected:injected"
    assert r.seconds == 0.01


def test_runner_exception_is_contained(tmp_path: Path) -> None:
    make_repo(tmp_path, "boom")

    def exploding_runner(name: str, cmd: str, repo_path: Path) -> RunResult:
        raise RuntimeError("kaboom")

    results = execute_runs([("boom", "x")], tmp_path, runner=exploding_runner)
    r = results[0]
    assert r.exit_code is None
    assert not r.skipped
    assert "kaboom" in r.stderr_tail


def test_results_sorted_by_name(tmp_path: Path) -> None:
    for name in ("zulu", "alpha", "mike"):
        make_repo(tmp_path, name)
    results = execute_runs(
        plan_runs(["zulu", "alpha", "mike"], f'{PY} -c "pass"'), tmp_path
    )
    assert [r.name for r in results] == ["alpha", "mike", "zulu"]


def test_execute_empty_plan() -> None:
    assert execute_runs([], Path("/nonexistent")) == []


def test_execute_never_raises_on_bad_repos_dir(tmp_path: Path) -> None:
    make_repo(tmp_path, "ghost")
    # repos_dir pointing elsewhere: the .git check fails -> skipped, no raise.
    results = execute_runs([("ghost", "echo hi")], tmp_path / "elsewhere")
    assert results[0].skipped


# ---------------------------------------------------------------------------
# RunResult JSON round trip
# ---------------------------------------------------------------------------


def test_run_result_json_roundtrip() -> None:
    r = RunResult(
        name="r1",
        command="pytest -q",
        exit_code=2,
        timed_out=False,
        skipped=False,
        skip_reason="",
        seconds=12.5,
        stdout_tail="out",
        stderr_tail="err",
    )
    raw = json.loads(json.dumps(to_dict(r)))
    rebuilt = from_dict(RunResult, raw)
    assert rebuilt == r


def test_run_result_roundtrip_skipped_variant() -> None:
    r = RunResult("r2", "cmd", None, False, True, "missing clone", 0.0, "", "")
    raw = json.loads(json.dumps(to_dict(r)))
    assert from_dict(RunResult, raw) == r


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------


def make_artifact(repos: list[dict]) -> dict:
    return {
        "run_id": "20260101-000000",
        "generated_at": "2026-01-01T00:00:00Z",
        "command": "pytest -q",
        "selector": "all",
        "repos": repos,
    }


def repo_row(name: str, exit_code: int | None, seconds: float, **kw: object) -> dict:
    base = {
        "name": name,
        "command": "pytest -q",
        "exit_code": exit_code,
        "timed_out": False,
        "skipped": False,
        "skip_reason": "",
        "seconds": seconds,
        "stdout_tail": "",
        "stderr_tail": "",
    }
    base.update(kw)
    return base


def test_summarize_counts_and_failures() -> None:
    artifact = make_artifact(
        [
            repo_row("a", 0, 1.0),
            repo_row("b", 3, 2.0),
            repo_row("c", None, 5.0, timed_out=True),
            repo_row("d", None, 0.0, skipped=True, skip_reason="missing clone"),
            repo_row("e", 1, 4.0),
        ]
    )
    s = summarize(artifact)
    assert s["total"] == 5
    assert s["ok"] == 1
    assert s["failed"] == 3  # b (3), c (timed out), e (1)
    assert s["timed_out"] == 1
    assert s["skipped"] == 1
    assert s["failures"] == [
        {"name": "b", "exit_code": 3},
        {"name": "c", "exit_code": None},
        {"name": "e", "exit_code": 1},
    ]


def test_summarize_slowest_top5() -> None:
    rows = [repo_row(f"r{i:02d}", 0, float(i)) for i in range(8)]
    slowest = summarize(make_artifact(rows))["slowest"]
    assert [s["name"] for s in slowest] == ["r07", "r06", "r05", "r04", "r03"]
    assert all(set(s) == {"name", "seconds"} for s in slowest)


def test_summarize_pure() -> None:
    artifact = make_artifact([repo_row("a", 0, 1.0)])
    import copy

    snapshot = copy.deepcopy(artifact)
    summarize(artifact)
    assert artifact == snapshot


# ---------------------------------------------------------------------------
# render_run_report
# ---------------------------------------------------------------------------


def test_render_is_deterministic() -> None:
    artifact = make_artifact(
        [
            repo_row("a", 0, 1.5),
            repo_row("b", 3, 2.0, stderr_tail="boom"),
        ]
    )
    s = summarize(artifact)
    assert render_run_report(artifact, s) == render_run_report(artifact, s)


def test_render_structure() -> None:
    artifact = make_artifact([repo_row("a", 0, 1.5), repo_row("b", 3, 2.0, stderr_tail="boom")])
    report = render_run_report(artifact, summarize(artifact))
    assert report.startswith("# Run Report: 20260101-000000")
    assert "`pytest -q`" in report
    assert "| Repo | Exit | Seconds | Timed Out | Skipped |" in report
    assert "| a | 0 | 1.500 | false | false |" in report
    assert "### b (exit 3)" in report
    assert "```text\nboom\n```" in report


def test_render_caps_stderr_tail() -> None:
    artifact = make_artifact([repo_row("big", 1, 1.0, stderr_tail="x" * 5000)])
    report = render_run_report(artifact, summarize(artifact))
    assert "x" * 1200 in report
    assert "x" * 1201 not in report


def test_render_no_failures_section_says_none() -> None:
    artifact = make_artifact([repo_row("a", 0, 1.0)])
    report = render_run_report(artifact, summarize(artifact))
    assert "## Failures" in report
    assert "None." in report


def test_render_marks_timeout_and_skip() -> None:
    artifact = make_artifact(
        [
            repo_row("t", None, 1.0, timed_out=True),
            repo_row("s", None, 0.0, skipped=True, skip_reason="missing clone"),
        ]
    )
    report = render_run_report(artifact, summarize(artifact))
    assert "| t | None | 1.000 | true | false |" in report
    assert "| s | None | 0.000 | false | true |" in report


# ---------------------------------------------------------------------------
# run_and_save
# ---------------------------------------------------------------------------


def test_run_and_save_persists_results(tmp_path: Path) -> None:
    make_repo(tmp_path / "repos", "saveable")
    run_id, artifact = run_and_save(
        ["saveable"],
        f'{PY} -c "print(\'saved\')"',
        project_root=tmp_path,
        selector_desc="lang:Python",
        run_id="20260902-120000",
    )
    assert run_id == "20260902-120000"
    assert set(artifact) == {"run_id", "generated_at", "command", "selector", "repos"}
    path = tmp_path / "output" / "data" / "runs" / run_id / "results.json"
    assert path.exists()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == artifact
    assert on_disk["repos"][0]["name"] == "saveable"
    assert "saved" in on_disk["repos"][0]["stdout_tail"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", on_disk["generated_at"])


def test_run_and_save_generates_default_run_id(tmp_path: Path) -> None:
    make_repo(tmp_path / "repos", "saveable2")
    run_id, _ = run_and_save(
        ["saveable2"], f"{PY} -c \"print('x')\"", project_root=tmp_path, selector_desc="all"
    )
    assert re.fullmatch(r"\d{8}-\d{6}", run_id)
    assert (tmp_path / "output" / "data" / "runs" / run_id / "results.json").exists()


def test_run_and_save_forwards_execute_kwargs(tmp_path: Path) -> None:
    make_repo(tmp_path / "repos", "no_git_here", with_git=False)
    _, artifact = run_and_save(
        ["no_git_here"],
        "echo hi",
        project_root=tmp_path,
        selector_desc="all",
        run_id="r-kwargs",
        tail_bytes=64,
    )
    assert artifact["repos"][0]["skipped"] is True
    assert artifact["repos"][0]["skip_reason"] == "missing clone"

class TestResolveAuto:
    """resolve_auto: capability filtering is pure and sorted."""

    def test_filters_and_maps(self) -> None:
        profiles = {
            "alpha": {"auto_cmds": {"test": "cargo test"}},
            "beta": {"auto_cmds": {"lint": "ruff check ."}},
            "gamma": {"auto_cmds": {}},
        }
        names, overrides, skipped = resolve_auto(
            ["gamma", "beta", "alpha"], profiles, "test"
        )
        assert names == ["alpha"]
        assert overrides == {"alpha": "cargo test"}
        assert skipped == ["beta", "gamma"]

    def test_no_capability_anywhere(self) -> None:
        names, overrides, skipped = resolve_auto(["a"], {"a": {}}, "lint")
        assert names == [] and overrides == {} and skipped == ["a"]

    def test_rejects_unknown_key(self) -> None:
        with pytest.raises(ValueError, match="unknown auto-command key"):
            resolve_auto(["a"], {"a": {}}, "deploy")


class TestForksFilter:
    def test_forks_false_excludes_fork_repos(self) -> None:
        profiles = {
            "own": {"primary_language": "Rust", "fork": False},
            "bun": {"primary_language": "Rust", "fork": True},
        }
        names = filter_repos(profiles, SelectorSpec(forks=False))
        assert names == ["own"]

    def test_forks_true_keeps_only_forks(self) -> None:
        profiles = {
            "own": {"primary_language": "Rust", "fork": False},
            "bun": {"primary_language": "Rust", "fork": True},
        }
        assert filter_repos(profiles, SelectorSpec(forks=True)) == ["bun"]

    def test_forks_none_keeps_everything(self) -> None:
        profiles = {
            "own": {"fork": False},
            "bun": {"fork": True},
        }
        assert filter_repos(profiles, SelectorSpec()) == ["bun", "own"]

    def test_missing_fork_key_treated_as_not_fork(self) -> None:
        profiles = {"plain": {}}
        assert filter_repos(profiles, SelectorSpec(forks=False)) == ["plain"]
        assert filter_repos(profiles, SelectorSpec(forks=True)) == []
