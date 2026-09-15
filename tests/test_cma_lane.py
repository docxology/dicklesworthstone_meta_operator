"""Tests for ``src/cma_lane.py`` — the code_meta_analysis orchestration lane.

Zero-mock: the cma CLI is faked with a REAL stdlib ``scripts/lanes.py``
executable in a tmp checkout (the "fake cma CLI via injected script path"
pattern); the runner seam accepts a plain injected Python function. Real
subprocess runs exercise ``uv run python scripts/lanes.py`` end to end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import OperatorConfig
from src.cma_lane import (
    CMA_AUTO_KEY,
    CMA_COMMAND_LABEL,
    LaneOutcome,
    _run_lane,
    build_cma_rows,
    build_cma_runner,
    lane_argv,
    parse_deps_report,
    read_issues_file,
    render_cma_section,
    resolve_cma_dir,
    run_cma_analyze,
)
from src.models import RunResult
from src.models import RunResult

DEPS_JSON = json.dumps(
    {
        "summary": {"edges": 1, "files_analyzed": 3},
        "central_files": [{"path": "src/a.py", "coupling": 0.5}],
    }
)

FAKE_LANES = """#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path

args = sys.argv[1:]
lane, repo = args[0], Path(args[1])
out = Path(args[args.index("--out") + 1]) if "--out" in args else None
if os.environ.get("CMA_TEST_SLEEP"):
    time.sleep(float(os.environ["CMA_TEST_SLEEP"]))
if lane == "issues":
    if repo.name == "failing":
        print("cma issues boom", file=sys.stderr)
        sys.exit(3)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"{repo.name}_issues.json"
    dest.write_text(
        json.dumps({"repo": repo.name, "root": str(repo), "issues": [{"id": "i1"}, {"id": "i2"}]}),
        encoding="utf-8",
    )
    print(f"wrote {dest} (2 issues)")
    if "--json" in args:
        print(json.dumps({"issues": []}))
elif lane == "deps":
    print(json.dumps({"summary": {"edges": 1}, "central_files": [{"path": "src/a.py", "coupling": 0.5}]}))
"""

def make_repo(root: Path, name: str, *, with_git: bool = True) -> Path:
    """Fake repo directory with (or without) a ``.git`` marker."""
    repo = root / name
    repo.mkdir(parents=True, exist_ok=True)
    if with_git:
        (repo / ".git").mkdir(exist_ok=True)
    return repo


def make_fake_cma(tmp_path: Path) -> Path:
    """Fake cma checkout: stdlib lanes CLI emitting the two dashboard signals."""
    cma = tmp_path / "fake_cma"
    (cma / "scripts").mkdir(parents=True)
    lanes = cma / "scripts" / "lanes.py"
    lanes.write_text(FAKE_LANES, encoding="utf-8")
    lanes.chmod(0o755)
    return cma


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_lane_argv_issues_and_deps(tmp_path: Path) -> None:
    cma = tmp_path / "cma"
    out = tmp_path / "out"
    issues = lane_argv("issues", tmp_path / "alpha", cma, out)
    deps = lane_argv("deps", tmp_path / "alpha", cma)
    assert issues[:6] == ["uv", "run", "python", "scripts/lanes.py", "issues", str((tmp_path / "alpha").resolve())]  # relative entry: cwd = cma_dir
    assert "--json" in issues and issues[issues.index("--out") + 1] == str(out.resolve())
    assert deps[:6] == ["uv", "run", "python", "scripts/lanes.py", "deps", str((tmp_path / "alpha").resolve())]
    assert "--out" not in deps
    assert "--json" in deps
    with pytest.raises(ValueError, match="lane must be one of"):
        lane_argv("plan", tmp_path / "alpha", cma)


def test_parse_deps_report_variants() -> None:
    parsed = parse_deps_report(DEPS_JSON)
    assert parsed is not None and parsed["summary"]["edges"] == 1
    noisy = "warning: VIRTUAL_ENV mismatch\n" + DEPS_JSON + "\n"
    assert parse_deps_report(noisy) == parsed
    assert parse_deps_report("") is None
    assert parse_deps_report("not json at all") is None
    assert parse_deps_report('{"summary": {}}') is None  # missing central_files


def test_read_issues_file_variants(tmp_path: Path) -> None:
    good = tmp_path / "alpha_issues.json"
    good.write_text(
        json.dumps({"repo": "alpha", "issues": [{"id": "i1"}, {"id": "i2"}]}),
        encoding="utf-8",
    )
    assert read_issues_file(good) == [{"id": "i1"}, {"id": "i2"}]
    assert read_issues_file(tmp_path / "absent_issues.json") is None
    corrupt = tmp_path / "corrupt_issues.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert read_issues_file(corrupt) is None
    wrong = tmp_path / "wrong_issues.json"
    wrong.write_text(json.dumps({"repo": "alpha"}), encoding="utf-8")
    assert read_issues_file(wrong) is None


def _rr(
    name: str,
    *,
    exit_code: int | None = 0,
    timed_out: bool = False,
    skipped: bool = False,
    stdout_tail: str = "",
) -> RunResult:
    return RunResult(
        name=name,
        command="cma:issues+deps",
        exit_code=exit_code,
        timed_out=timed_out,
        skipped=skipped,
        skip_reason="missing clone" if skipped else "",
        seconds=1.0,
        stdout_tail=stdout_tail,
        stderr_tail="",
    )


def test_build_cma_rows_happy_and_failures(tmp_path: Path) -> None:
    out_dir = tmp_path
    (out_dir / "alpha_issues.json").write_text(
        json.dumps({"issues": [{"id": "i1"}, {"id": "i2"}, {"id": "i3"}]}),
        encoding="utf-8",
    )
    results = [
        _rr("alpha", stdout_tail=DEPS_JSON),
        _rr("beta", stdout_tail=DEPS_JSON),  # ok exit but no issues file
        _rr("gamma", exit_code=3, stdout_tail="boom"),  # failed lanes
        _rr("delta", exit_code=None, timed_out=True, stdout_tail=DEPS_JSON),
        _rr("epsilon", skipped=True),
    ]
    rows = build_cma_rows(results, out_dir)
    assert list(rows) == ["alpha", "beta", "delta", "gamma"]  # skipped excluded, sorted
    assert rows["alpha"] == {
        "issues_count": 3,
        "central_file": "src/a.py",
        "coupling": 0.5,
        "lanes": {"issues": "ok", "deps": "ok"},
        "status": "ok",
    }
    assert rows["beta"]["issues_count"] is None and rows["beta"]["status"] == "failed"
    assert rows["beta"]["lanes"] == {"issues": "failed", "deps": "ok"}
    assert rows["gamma"]["lanes"] == {"issues": "failed", "deps": "failed"}
    assert rows["delta"]["lanes"] == {"issues": "failed", "deps": "failed"}


def test_resolve_cma_dir(tmp_path: Path) -> None:
    cma = make_fake_cma(tmp_path)
    config = OperatorConfig(cma_dir="fake_cma")
    assert resolve_cma_dir(config, tmp_path) == cma.resolve()
    with pytest.raises(FileNotFoundError, match="cma_dir in data/operator_config.yaml"):
        resolve_cma_dir(OperatorConfig(cma_dir="nowhere"), tmp_path)


# ---------------------------------------------------------------------------
# run_cma_analyze — injected runner (fake cma CLI as a plain function)
# ---------------------------------------------------------------------------


def _injected_cma_runner(out_dir: Path):
    """Plain-function fake cma CLI: alpha ok, beta lane-fails, writes artifacts."""

    def runner(name: str, cmd: str, repo_path: Path) -> RunResult:
        if name == "alpha":
            (Path(out_dir) / "alpha_issues.json").write_text(
                json.dumps({"repo": name, "issues": [{"id": "i1"}, {"id": "i2"}]}),
                encoding="utf-8",
            )
            return RunResult(
                name=name,
                command=cmd,
                exit_code=0,
                timed_out=False,
                skipped=False,
                skip_reason="",
                seconds=0.5,
                stdout_tail=DEPS_JSON,
                stderr_tail="",
            )
        return RunResult(
            name=name,
            command=cmd,
            exit_code=2,
            timed_out=False,
            skipped=False,
            skip_reason="",
            seconds=0.2,
            stdout_tail="",
            stderr_tail="cma exploded",
        )

    return runner


def test_run_cma_analyze_injected_runner_failure_isolation(tmp_path: Path) -> None:
    make_fake_cma(tmp_path)  # satisfies resolve_cma_dir; runner is injected
    repos = tmp_path / "repos"
    make_repo(repos, "alpha")
    make_repo(repos, "beta")
    make_repo(repos, "gamma", with_git=False)
    out_dir = tmp_path / "output" / "data" / "cma" / "testrun"
    run_id, artifact = run_cma_analyze(
        ["alpha", "beta", "gamma"],
        project_root=tmp_path,
        config=OperatorConfig(cma_dir="fake_cma", run_workers=2),
        selector_desc="test",
        run_id="testrun",
        runner=_injected_cma_runner(out_dir),
    )
    assert run_id == "testrun"
    assert artifact["command"] == CMA_COMMAND_LABEL
    assert [r["name"] for r in artifact["repos"]] == ["alpha", "beta", "gamma"]
    by_name = {r["name"]: r for r in artifact["repos"]}
    assert by_name["gamma"]["skipped"] is True
    assert by_name["beta"]["exit_code"] == 2
    # failure isolation: beta is a failed cma row, alpha fully ok, gamma no row
    assert artifact["cma"]["alpha"]["status"] == "ok"
    assert artifact["cma"]["alpha"]["issues_count"] == 2
    assert artifact["cma"]["beta"]["status"] == "failed"
    assert "gamma" not in artifact["cma"]
    persisted = json.loads(
        (tmp_path / "output" / "data" / "runs" / "testrun" / "results.json").read_text()
    )
    assert persisted["cma"]["alpha"]["central_file"] == "src/a.py"


# ---------------------------------------------------------------------------
# run_cma_analyze — real subprocess against the fake cma CLI
# ---------------------------------------------------------------------------


def test_run_cma_analyze_real_subprocess(tmp_path: Path) -> None:
    cma = make_fake_cma(tmp_path)
    repos = tmp_path / "repos"
    make_repo(repos, "alpha")
    make_repo(repos, "failing")
    make_repo(repos, "noclone", with_git=False)
    run_id, artifact = run_cma_analyze(
        ["alpha", "failing", "noclone"],
        project_root=tmp_path,
        config=OperatorConfig(cma_dir="fake_cma", run_workers=2, run_timeout_s=300),
        selector_desc="test",
        run_id="subproctest",
    )
    rows = artifact["cma"]
    assert rows["alpha"]["status"] == "ok"
    assert rows["alpha"]["issues_count"] == 2
    assert rows["alpha"]["central_file"] == "src/a.py"
    assert rows["failing"]["status"] == "failed"
    # lanes are independent: deps succeeded even though issues exited 3
    assert rows["failing"]["lanes"] == {"issues": "failed", "deps": "ok"}
    assert rows["failing"]["issues_count"] is None
    assert "noclone" not in rows
    by_name = {r["name"]: r for r in artifact["repos"]}
    assert by_name["failing"]["exit_code"] == 3
    assert by_name["noclone"]["skipped"] is True
    assert "boom" in by_name["failing"]["stderr_tail"]
    assert (tmp_path / "output" / "data" / "cma" / "subproctest" / "alpha_issues.json").exists()


# ---------------------------------------------------------------------------
# Timeout path
# ---------------------------------------------------------------------------


def test_run_lane_timeout_is_typed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cma = make_fake_cma(tmp_path)
    monkeypatch.setenv("CMA_TEST_SLEEP", "5")
    outcome = _run_lane(
        lane_argv("deps", tmp_path / "alpha", cma),
        cma,
        timeout_s=1,
        tail_bytes=2000,
    )
    assert outcome.timed_out is True
    assert outcome.exit_code is None


def test_build_cma_rows_timed_out_combined_row(tmp_path: Path) -> None:
    rows = build_cma_rows([_rr("alpha", exit_code=None, timed_out=True)], tmp_path)
    assert rows["alpha"]["lanes"] == {"issues": "failed", "deps": "failed"}
    assert rows["alpha"]["status"] == "failed"
    assert rows["alpha"]["issues_count"] is None


# ---------------------------------------------------------------------------
# Combined runner semantics
# ---------------------------------------------------------------------------


def test_build_cma_runner_combines_lane_exit_codes(tmp_path: Path) -> None:
    cma = make_fake_cma(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    runner = build_cma_runner(cma, out_dir, timeout_s=300, tail_bytes=20000)
    repo = make_repo(tmp_path, "alpha")
    result = runner("alpha", "cma:issues+deps", repo)
    assert result.exit_code == 0
    assert result.command == "cma:issues+deps"
    assert "central_files" in result.stdout_tail
    assert result.seconds > 0.0

    (tmp_path / "failing").mkdir()
    (tmp_path / "failing" / ".git").mkdir()
    failed = runner("failing", "cma:issues+deps", tmp_path / "failing")
    assert failed.exit_code == 3
    assert "boom" in failed.stderr_tail


def test_render_cma_section_deterministic(tmp_path: Path) -> None:
    rows = {
        "alpha": {
            "issues_count": 3,
            "central_file": "src/a.py",
            "coupling": 0.5,
            "lanes": {"issues": "ok", "deps": "ok"},
            "status": "ok",
        },
        "beta": {
            "issues_count": None,
            "central_file": None,
            "coupling": None,
            "lanes": {"issues": "failed", "deps": "failed"},
            "status": "failed",
        },
    }
    a, b = render_cma_section(rows), render_cma_section(rows)
    assert a == b
    assert "| alpha | 3 | src/a.py | 0.5 | ok | ok | ok |" in a
    assert "| beta | — | — | — | failed | failed | failed |" in a
    assert render_cma_section({}) == ""
    assert "alpha" in render_cma_section({"alpha": None})  # missing fields degrade to —