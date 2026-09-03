"""Tests for ``src/health_gate.py`` — real output trees, real git clones, offline.

The fixture builds a complete mini output tree (two bare->work->repos clones,
registry, upstream status, inventory, dashboard, catalog) and then mutates
exactly one artifact per case, asserting the exact failed check id.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from src import project_paths
from src.health_gate import CHECK_IDS, load_gate, run_gate, save_gate


def _write_json(path: Path, payload: dict) -> None:
    """Write a fixture JSON artifact in the same format jsonio produces."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

REPO_NAMES = ("alpha", "beta")
FAKE_SHA = "a" * 40
FAKE_DATE = "2026-08-01T00:00:00Z"


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def _git(args: list[str], cwd: Path) -> None:
    _run(["git", *args], cwd=cwd)


def _make_clone(repos_root: Path, scratch: Path, name: str) -> None:
    """bare -> work (commit, push) -> repos/<name>: a real clone chain, offline."""
    bare = scratch / f"{name}.git"
    _run(["git", "init", "--bare", "-b", "main", str(bare)], cwd=scratch)
    work = scratch / f"work_{name}"
    _git(["clone", str(bare), str(work)], cwd=scratch)
    _git(["config", "user.email", "test@example.com"], cwd=work)
    _git(["config", "user.name", "Test"], cwd=work)
    (work / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    _git(["add", "."], cwd=work)
    _git(["commit", "-m", f"init {name}"], cwd=work)
    _git(["push", "origin", "main"], cwd=work)
    _git(["clone", str(bare), str(repos_root / name)], cwd=scratch)


def _meta(name: str) -> dict:
    return {
        "name": name,
        "html_url": f"https://github.com/Dicklesworthstone/{name}",
        "clone_url": f"https://github.com/Dicklesworthstone/{name}.git",
        "default_branch": "main",
        "language": "Python",
        "description": f"demo repo {name}",
        "size_kb": 11,
        "pushed_at": "2026-08-01T00:00:00Z",
        "fork": False,
        "archived": False,
        "topics": [],
    }


def _upstream_entry(name: str, state: str = "on_upstream") -> dict:
    return {
        "name": name,
        "default_branch": "main",
        "checked_out_branch": "main",
        "head_sha": FAKE_SHA,
        "remote_sha": FAKE_SHA,
        "on_upstream_default": state in {"on_upstream"},
        "ahead": 0,
        "behind": 0,
        "dirty": False,
        "detached": False,
        "unborn": False,
        "state": state,
    }


def _profile(name: str, date: str = FAKE_DATE) -> dict:
    return {
        "name": name,
        "primary_language": "Python",
        "languages": {".py": 42},
        "total_loc": 42,
        "file_count": 3,
        "readme_title": name,
        "readme_summary": f"summary of {name}",
        "manifests": {"pyproject.toml": "pyproject.toml"},
        "entry_points": [f"{name}/cli.py"],
        "has_tests": True,
        "test_cmd": "pytest -q",
        "auto_cmds": {"test": "pytest -q"},
        "last_commit_sha": FAKE_SHA,
        "last_commit_date": date,
        "last_commit_message": f"init {name}",
    }


def _registry_payload(names: tuple[str, ...] = REPO_NAMES) -> dict:
    return {
        "generated_at": "2026-08-02T00:00:00Z",
        "github_user": "Dicklesworthstone",
        "include_forks": True,
        "repos": [_meta(n) for n in names],
    }


def build_tree(root: Path, scratch: Path) -> None:
    """Build a fully passing mini output tree under ``root``."""
    scratch.mkdir(parents=True, exist_ok=True)
    ddir = project_paths.data_dir(root)
    ddir.mkdir(parents=True, exist_ok=True)
    project_paths.web_dir(root).mkdir(parents=True, exist_ok=True)
    repos_root = project_paths.repos_dir(root)
    repos_root.mkdir(parents=True, exist_ok=True)
    for name in REPO_NAMES:
        _make_clone(repos_root, scratch, name)
    _write_json(ddir / project_paths.REPO_REGISTRY, _registry_payload())
    _write_json(ddir / project_paths.UPSTREAM_STATUS, {
        "generated_at": "2026-08-02T00:00:00Z",
        "checked": len(REPO_NAMES),
        "ok": len(REPO_NAMES),
        "repos": [_upstream_entry(n) for n in REPO_NAMES],
    })
    _write_json(ddir / project_paths.INVENTORY, {
        "generated_at": "2026-08-02T00:00:00Z",
        "repos": [_profile(n) for n in REPO_NAMES],
    })
    (project_paths.web_dir(root) / project_paths.DASHBOARD).write_text(
        "<html><body>" + "x" * 12000 + "</body></html>", encoding="utf-8"
    )
    (ddir / project_paths.CORPUS_CATALOG).write_text(
        "# Corpus Catalog\n\nall good\n", encoding="utf-8"
    )


def _by_id(report):
    return {c.check_id: c for c in report.checks}


def _assert_only_fails(report, *failed: str) -> None:
    by_id = _by_id(report)
    assert set(by_id) == set(CHECK_IDS)
    for cid in CHECK_IDS:
        if cid in failed:
            assert not by_id[cid].passed, (cid, by_id[cid].detail)
        else:
            assert by_id[cid].passed, (cid, by_id[cid].detail)


def test_complete_tree_passes(tmp_path: Path) -> None:
    build_tree(tmp_path, tmp_path / "scratch")
    report = run_gate(tmp_path)
    assert report.passed
    by_id = _by_id(report)
    assert "2 repos" in by_id["registry_present"].detail
    assert by_id["runs_present"].detail == "no runs yet (advisory)"


def test_missing_clone_fails_only_clones_complete(tmp_path: Path) -> None:
    build_tree(tmp_path, tmp_path / "scratch")
    (tmp_path / "repos" / "beta").rename(tmp_path / "scratch" / "stashed_beta")
    report = run_gate(tmp_path)
    _assert_only_fails(report, "clones_complete")
    detail = _by_id(report)["clones_complete"].detail
    assert "beta" in detail and "20_clone_corpus.py" in detail


def test_offending_upstream_fails_only_upstream_check(tmp_path: Path) -> None:
    build_tree(tmp_path, tmp_path / "scratch")
    ddir = project_paths.data_dir(tmp_path)
    raw = _read_json(ddir / project_paths.UPSTREAM_STATUS)
    raw["repos"][1]["state"] = "behind"
    raw["ok"] = 1
    _write_json(ddir / project_paths.UPSTREAM_STATUS, raw)
    report = run_gate(tmp_path)
    _assert_only_fails(report, "upstream_all_ok")
    assert "beta: behind" in _by_id(report)["upstream_all_ok"].detail


def test_missing_inventory_entry_fails_only_inventory_complete(tmp_path: Path) -> None:
    build_tree(tmp_path, tmp_path / "scratch")
    ddir = project_paths.data_dir(tmp_path)
    _write_json(
        ddir / project_paths.INVENTORY,
        {"generated_at": "2026-08-02T00:00:00Z", "repos": [_profile("alpha")]},
    )
    report = run_gate(tmp_path)
    _assert_only_fails(report, "inventory_complete")
    assert "beta" in _by_id(report)["inventory_complete"].detail


def test_truncated_dashboard_fails_only_dashboard_present(tmp_path: Path) -> None:
    build_tree(tmp_path, tmp_path / "scratch")
    (project_paths.web_dir(tmp_path) / project_paths.DASHBOARD).write_text(
        "<html>tiny", encoding="utf-8"
    )
    report = run_gate(tmp_path)
    _assert_only_fails(report, "dashboard_present")


def test_missing_registry_fails_with_hint(tmp_path: Path) -> None:
    report = run_gate(tmp_path)
    by_id = _by_id(report)
    assert not by_id["registry_present"].passed
    assert "scripts/10_build_registry.py" in by_id["registry_present"].detail
    assert not report.passed


def test_expected_count_mismatch_fails_registry_check(tmp_path: Path) -> None:
    build_tree(tmp_path, tmp_path / "scratch")
    mismatch = run_gate(tmp_path, expected_count=5)
    _assert_only_fails(mismatch, "registry_present")
    assert "expected 5, got 2" in _by_id(mismatch)["registry_present"].detail
    match = run_gate(tmp_path, expected_count=2)
    assert match.passed


def test_missing_clones_capped_at_ten(tmp_path: Path) -> None:
    names = tuple(f"repo{i:02d}" for i in range(12))
    ddir = project_paths.data_dir(tmp_path)
    ddir.mkdir(parents=True, exist_ok=True)
    project_paths.web_dir(tmp_path).mkdir(parents=True, exist_ok=True)
    _write_json(ddir / project_paths.REPO_REGISTRY, _registry_payload(names))
    _write_json(ddir / project_paths.UPSTREAM_STATUS, {
        "generated_at": "2026-08-02T00:00:00Z",
        "checked": len(names),
        "ok": len(names),
        "repos": [_upstream_entry(n) for n in names],
    })
    _write_json(
        ddir / project_paths.INVENTORY,
        {
            "generated_at": "2026-08-02T00:00:00Z",
            "repos": [_profile(n) for n in names],
        },
    )
    (project_paths.web_dir(tmp_path) / project_paths.DASHBOARD).write_text(
        "<html><body>" + "x" * 12000 + "</body></html>", encoding="utf-8"
    )
    (ddir / project_paths.CORPUS_CATALOG).write_text("# Corpus Catalog\n", encoding="utf-8")
    report = run_gate(tmp_path)
    _assert_only_fails(report, "clones_complete")
    detail = _by_id(report)["clones_complete"].detail
    assert detail.count("repo") == 10
    assert "+2 more)" in detail


def test_runs_present_reports_last_run(tmp_path: Path) -> None:
    build_tree(tmp_path, tmp_path / "scratch")
    rdir = project_paths.runs_dir(tmp_path)
    for rid in ("2026-01-01_a", "2026-01-02_b"):
        (rdir / rid).mkdir(parents=True)
        _write_json(rdir / rid / "results.json", {"run_id": rid, "repos": []})
    report = run_gate(tmp_path)
    runs = _by_id(report)["runs_present"]
    assert runs.passed and runs.detail == "last run 2026-01-02_b"


def test_gate_report_json_round_trip(tmp_path: Path) -> None:
    build_tree(tmp_path, tmp_path / "scratch")
    report = run_gate(tmp_path)
    save_gate(report, tmp_path)
    loaded = load_gate(tmp_path)
    assert loaded.generated_at == report.generated_at
    assert loaded.passed == report.passed
    assert loaded.checks == report.checks
    assert isinstance(loaded.checks[0], object)
    assert type(loaded.checks[0]).__name__ == "GateCheck"

def test_empty_upstream_entries_fail(tmp_path: Path) -> None:
    """An upstream artifact with zero entries must fail, not silently pass."""
    build_tree(tmp_path, tmp_path / "scratch")
    _write_json(
        project_paths.data_dir(tmp_path) / project_paths.UPSTREAM_STATUS,
        {"generated_at": "x", "checked": 0, "ok": 0, "repos": []},
    )
    report = run_gate(tmp_path)
    check = _by_id(report)["upstream_all_ok"]
    assert not check.passed
    assert "no repos entries" in check.detail


def test_malformed_upstream_entries_fail(tmp_path: Path) -> None:
    """Non-object entries are corruption, not data: fail loudly."""
    build_tree(tmp_path, tmp_path / "scratch")
    _write_json(
        project_paths.data_dir(tmp_path) / project_paths.UPSTREAM_STATUS,
        {"generated_at": "x", "checked": 2, "ok": 0, "repos": ["not-a-dict"]},
    )
    report = run_gate(tmp_path)
    check = _by_id(report)["upstream_all_ok"]
    assert not check.passed
    assert "malformed" in check.detail
