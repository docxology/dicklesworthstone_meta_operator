"""Tests for ``src/dashboard.py`` — payload loading, summary, deterministic renders."""

from __future__ import annotations

from pathlib import Path

import pytest

import json

from src import project_paths
from src.dashboard import (
    compute_summary,
    load_payload,
    render_catalog,
    render_dashboard,
    write_artifacts,
)


def _write_json(path: Path, payload: dict) -> None:
    """Write a fixture JSON artifact in the same format jsonio produces."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

FAKE_DATE = "2026-08-01T00:00:00Z"
OLD_DATE = "2020-01-01T00:00:00Z"


def _meta(name: str, language: str, size_kb: int = 10, fork: bool = False) -> dict:
    return {
        "name": name,
        "html_url": f"https://github.com/Dicklesworthstone/{name}",
        "clone_url": f"https://github.com/Dicklesworthstone/{name}.git",
        "default_branch": "main",
        "language": language,
        "description": f"demo repo {name}",
        "size_kb": size_kb,
        "pushed_at": "2026-08-01T00:00:00Z",
        "fork": fork,
        "archived": False,
        "topics": [],
    }


def _upstream_entry(name: str, state: str = "on_upstream") -> dict:
    return {
        "name": name,
        "default_branch": "main",
        "checked_out_branch": "main",
        "head_sha": "a" * 40,
        "remote_sha": "a" * 40,
        "on_upstream_default": True,
        "ahead": 0,
        "behind": 0,
        "dirty": False,
        "detached": False,
        "unborn": False,
        "state": state,
    }


def _profile(name: str, total_loc: int, date: str = FAKE_DATE) -> dict:
    return {
        "name": name,
        "primary_language": "Python",
        "languages": {".py": total_loc},
        "total_loc": total_loc,
        "file_count": 3,
        "readme_title": name,
        "readme_summary": f"summary of {name}",
        "manifests": {"pyproject.toml": "pyproject.toml"},
        "entry_points": [f"{name}/cli.py"],
        "has_tests": True,
        "test_cmd": "pytest -q",
        "auto_cmds": {"test": "pytest -q", "lint": "ruff check ."},
        "last_commit_sha": "b" * 40,
        "last_commit_date": date,
        "last_commit_message": f"init {name}",
    }


def _registry(repos: list[dict]) -> dict:
    return {
        "generated_at": "2026-08-02T00:00:00Z",
        "github_user": "Dicklesworthstone",
        "include_forks": True,
        "repos": repos,
    }


def _upstream(entries: list[dict]) -> dict:
    return {
        "generated_at": "2026-08-02T00:00:00Z",
        "checked": len(entries),
        "ok": sum(1 for e in entries if e["state"] == "on_upstream"),
        "repos": entries,
    }


def _inventory(profiles: list[dict]) -> dict:
    return {"generated_at": "2026-08-02T00:00:00Z", "repos": profiles}


def _write_tree(
    root: Path,
    *,
    repos: list[dict],
    upstream: dict | None,
    inventory: dict | None,
    run: dict | None = None,
) -> None:
    ddir = project_paths.data_dir(root)
    ddir.mkdir(parents=True, exist_ok=True)
    _write_json(ddir / project_paths.REPO_REGISTRY, _registry(repos))
    if upstream is not None:
        _write_json(ddir / project_paths.UPSTREAM_STATUS, upstream)
    if inventory is not None:
        _write_json(ddir / project_paths.INVENTORY, inventory)
    if run is not None:
        rdir = project_paths.runs_dir(root)
        (rdir / run["run_id"]).mkdir(parents=True, exist_ok=True)
        _write_json(rdir / run["run_id"] / "results.json", run)


def _full_payload_args() -> dict:
    repos = [
        _meta("alpha", "Python", 100),
        _meta("beta", "Go", 20),
        _meta("gamma", "Python", 30, fork=True),
    ]
    return {
        "repos": repos,
        "upstream": _upstream(
            [
                _upstream_entry("alpha"),
                _upstream_entry("beta"),
                _upstream_entry("gamma", "behind"),
            ]
        ),
        "inventory": _inventory(
            [
                {
                    **{
                        "name": "alpha",
                        "primary_language": "Python",
                        "languages": {".py": 1200},
                        "total_loc": 1200,
                        "file_count": 30,
                        "readme_title": "alpha",
                        "readme_summary": "summary of alpha",
                        "manifests": {"pyproject.toml": "pyproject.toml"},
                        "entry_points": ["alpha/cli.py"],
                        "has_tests": True,
                        "test_cmd": "pytest -q",
                        "auto_cmds": {"test": "pytest -q"},
                        "last_commit_sha": "b" * 40,
                        "last_commit_date": FAKE_DATE,
                        "last_commit_message": "init alpha",
                    }
                },
                {
                    "name": "beta",
                    "primary_language": "Go",
                    "languages": {".go": 400},
                    "total_loc": 400,
                    "file_count": 10,
                    "readme_title": "beta",
                    "readme_summary": "summary of beta",
                    "manifests": {"go.mod": "go.mod"},
                    "entry_points": ["beta/main.go"],
                    "has_tests": False,
                    "test_cmd": None,
                    "auto_cmds": {},
                    "last_commit_sha": "c" * 40,
                    "last_commit_date": OLD_DATE,
                    "last_commit_message": "init beta",
                },
            ]
        ),
    }


def test_load_payload_shape_and_missing_artifacts(tmp_path: Path) -> None:
    args = _full_payload_args()
    _write_tree(tmp_path, **args)
    payload = load_payload(tmp_path)
    assert set(payload) == {
        "generated_at",
        "github_user",
        "include_forks",
        "repos",
        "upstream",
        "inventory",
        "run",
        "runs_history",
    }
    assert payload["github_user"] == "Dicklesworthstone"
    assert payload["include_forks"] is True
    assert len(payload["repos"]) == 3
    assert payload["upstream"] is not None and payload["inventory"] is not None
    assert payload["run"] is None
    assert payload["generated_at"].endswith("Z")


def test_load_payload_missing_registry_raises_with_hint(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="10_build_registry"):
        load_payload(tmp_path)


def test_load_payload_run_selection(tmp_path: Path) -> None:
    _write_tree(tmp_path, repos=[_meta("alpha", "Python")], upstream=None, inventory=None)
    rdir = project_paths.runs_dir(tmp_path)
    for rid in ("2026-01-01_a", "2026-01-02_b"):
        (rdir / rid).mkdir(parents=True)
        _write_json(rdir / rid / "results.json", {"run_id": rid, "repos": []})
    assert load_payload(tmp_path)["run"]["run_id"] == "2026-01-02_b"
    assert load_payload(tmp_path, run_id="2026-01-01_a")["run"]["run_id"] == "2026-01-01_a"
    with pytest.raises(RuntimeError, match="run 'absent' not found"):
        load_payload(tmp_path, run_id="absent")


def test_compute_summary_aggregates(tmp_path: Path) -> None:
    payload = {
        "repos": _full_payload_args()["repos"],
        "upstream": _full_payload_args()["upstream"],
        "inventory": _full_payload_args()["inventory"],
        "run": None,
    }
    s = compute_summary(payload)
    assert s["total"] == 3
    assert s["forks"] == 1
    assert s["languages"] == {"Python": 2, "Go": 1}  # desc by count, then name
    assert s["upstream_states"] == {"on_upstream": 2, "behind": 1}
    assert s["upstream_ok"] == 2
    assert s["upstream_not_ok"] == 1
    assert s["total_loc"] == 1600
    assert s["total_size_kb"] == 150
    assert s["stale_days_max"] is not None and s["stale_days_max"] > 2000
    assert [t["name"] for t in s["top_by_loc"]] == ["alpha", "beta"]


def test_compute_summary_empty_optional_artifacts() -> None:
    s = compute_summary({"repos": [], "upstream": None, "inventory": None, "run": None})
    assert s["total"] == 0 and s["upstream_ok"] == 0 and s["upstream_not_ok"] == 0
    assert s["total_loc"] == 0 and s["stale_days_max"] is None


def test_render_dashboard_deterministic_and_content(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-08-02T00:00:00Z",
        "github_user": "Dicklesworthstone",
        "include_forks": True,
        "run": None,
        **_full_payload_args(),
    }
    summary = compute_summary(payload)
    html_a = render_dashboard(payload, summary)
    html_b = render_dashboard(payload, summary)
    assert html_a == html_b
    for repo in ("alpha", "beta", "gamma"):
        assert f">{repo}</a>" in html_a
    assert 'id="filter"' in html_a
    assert "chip-on_upstream" in html_a and "chip-behind" in html_a
    assert "chip-missing" in html_a  # full state legend renders every class
    assert "window.__REPO_DATA__" in html_a
    assert "not built yet" not in html_a
    assert html_a.count("<style>") == 1 and html_a.count("<script>") == 1


def test_render_dashboard_optional_artifact_panels() -> None:
    payload = {
        "generated_at": "2026-08-02T00:00:00Z",
        "github_user": "Dicklesworthstone",
        "include_forks": True,
        "repos": [_meta("alpha", "Python")],
        "upstream": None,
        "inventory": None,
        "run": None,
    }
    html = render_dashboard(payload, compute_summary(payload))
    assert html.count("not built yet") == 2
    assert 'data-state=""' in html


def test_render_dashboard_runs_section() -> None:
    run = {
        "run_id": "2026-01-02_b",
        "generated_at": "2026-01-02T00:00:00Z",
        "command": "pytest -q",
        "selector": "all",
        "repos": [
            {
                "name": "alpha",
                "command": "pytest -q",
                "exit_code": 0,
                "timed_out": False,
                "skipped": False,
                "skip_reason": "",
                "seconds": 1.5,
                "stdout_tail": "1 passed",
                "stderr_tail": "warning: deprecated thing\nline two <script>",
            },
            {
                "name": "beta",
                "command": "pytest -q",
                "exit_code": None,
                "timed_out": True,
                "skipped": False,
                "skip_reason": "",
                "seconds": 600.0,
                "stdout_tail": "",
                "stderr_tail": "killed after timeout",
            },
        ],
    }
    payload = {
        "generated_at": "2026-08-02T00:00:00Z",
        "github_user": "Dicklesworthstone",
        "include_forks": True,
        "repos": [_meta("alpha", "Python"), _meta("beta", "Go")],
        "upstream": None,
        "inventory": None,
        "run": run,
    }
    html = render_dashboard(payload, compute_summary(payload))
    assert 'class="runs"' in html and "<details>" in html
    assert "2026-01-02_b" in html
    assert "exit-ok" in html and "exit-timeout" in html
    # raw </script> inside stderr must not break out of the script/data blocks
    assert "<script>line two" not in html


def test_render_catalog_sections_sorted_and_deterministic() -> None:
    payload = {
        "generated_at": "2026-08-02T00:00:00Z",
        "github_user": "Dicklesworthstone",
        "include_forks": True,
        "run": None,
        **_full_payload_args(),
    }
    summary = compute_summary(payload)
    cat_a = render_catalog(payload, summary)
    cat_b = render_catalog(payload, summary)
    assert cat_a == cat_b
    assert cat_a.startswith("# Corpus Catalog")
    assert "Generated: 2026-08-02T00:00:00Z" in cat_a
    assert "3 repos (1 forks)" in cat_a
    go_at = cat_a.index("## Go")
    py_at = cat_a.index("## Python")
    assert go_at < py_at  # language sections sorted by name
    assert "| Repo | Upstream | LOC | Last commit | Fork | Description |" in cat_a
    assert "[alpha](https://github.com/Dicklesworthstone/alpha)" in cat_a
    assert "| on_upstream |" in cat_a and "| behind |" in cat_a
    assert "| no |" in cat_a and "| yes |" in cat_a
    assert "1200" in cat_a and FAKE_DATE in cat_a


def test_write_artifacts_writes_both_files(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-08-02T00:00:00Z",
        "github_user": "Dicklesworthstone",
        "include_forks": True,
        "run": None,
        **_full_payload_args(),
    }
    summary = compute_summary(payload)
    dash_path, cat_path = write_artifacts(payload, summary, tmp_path)
    assert dash_path == project_paths.web_dir(tmp_path) / project_paths.DASHBOARD
    assert cat_path == project_paths.data_dir(tmp_path) / project_paths.CORPUS_CATALOG
    assert dash_path.is_file() and dash_path.stat().st_size > 10_000
    assert cat_path.is_file() and cat_path.stat().st_size > 0
    assert dash_path.read_text(encoding="utf-8") == render_dashboard(payload, summary)
    assert cat_path.read_text(encoding="utf-8") == render_catalog(payload, summary)

def test_load_payload_builds_runs_history(tmp_path: Path) -> None:
    """Two runs -> per-repo oldest-first history, bounded, corrupt-safe."""
    _write_tree(tmp_path, repos=[_meta("alpha", "Python")], upstream=None, inventory=None)
    rdir = project_paths.runs_dir(tmp_path)
    for rid, exit_code in (("2026-01-01_a", 0), ("2026-01-02_b", 3)):
        (rdir / rid).mkdir(parents=True)
        _write_json(
            rdir / rid / "results.json",
            {
                "run_id": rid,
                "command": "git pull --ff-only",
                "selector": "all",
                "repos": [
                    {"name": "alpha", "command": "git pull --ff-only", "exit_code": exit_code,
                     "timed_out": False, "skipped": False, "seconds": 0.1,
                     "stdout_tail": "", "stderr_tail": "", "skip_reason": ""}
                ],
            },
        )
    (rdir / "2026-01-00_broken").mkdir()
    (rdir / "2026-01-00_broken" / "results.json").write_text("{oops", encoding="utf-8")

    payload = load_payload(tmp_path)
    hist = payload["runs_history"]["alpha"]
    assert [h["run_id"] for h in hist] == ["2026-01-01_a", "2026-01-02_b"]
    assert hist[0]["exit_code"] == 0 and hist[1]["exit_code"] == 3


def test_render_drawer_shows_run_history(tmp_path: Path) -> None:
    payload = _full_payload_args()
    payload["runs_history"] = {
        "alpha": [
            {"run_id": "20260903-074158", "command": "git pull --ff-only",
             "exit_code": 0, "timed_out": False, "skipped": False}
        ]
    }
    summary = compute_summary(payload)
    html = render_dashboard(payload, summary)
    assert "Run history" in html
    assert "20260903-074158" in html
    assert "__RUN_HISTORY__" in html
    # deterministic: two renders identical
    assert render_dashboard(payload, summary) == html


def test_render_no_history_placeholder(tmp_path: Path) -> None:
    payload = _full_payload_args()
    payload["runs_history"] = {}
    html = render_dashboard(payload, compute_summary(payload))
    assert "__RUN_HISTORY__={}" in html
