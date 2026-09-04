"""Tests for ``src/figures.py`` — real matplotlib PNGs, byte-level determinism.

No mocks: every builder runs against plain fixture dicts and writes real PNG
files under ``tmp_path``; determinism is asserted by re-rendering and comparing
file bytes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.figures import (
    FIGURE_FILENAMES,
    build_all_figures,
    build_language_distribution_figure,
    build_loc_size_figure,
    build_state_distribution_figure,
    build_staleness_figure,
)

NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)


def _statuses() -> list[dict]:
    return [
        {"name": "alpha", "state": "on_upstream"},
        {"name": "beta", "state": "behind"},
        {"name": "gamma", "state": "behind"},
        {"name": "delta", "state": "unborn"},
    ]


def _repos() -> list[dict]:
    return [
        {"name": "alpha", "language": "Python"},
        {"name": "beta", "language": "Python"},
        {"name": "gamma", "language": "TypeScript"},
        {"name": "delta", "language": None},
        {"name": "epsilon", "language": ""},
    ]


def _registry() -> dict:
    """Registry payload whose repos carry the size_kb the inventory lacks."""
    sizes = {"alpha": 4321, "beta": 18750, "gamma": 640}
    return {
        "generated_at": "2026-08-02T00:00:00Z",
        "github_user": "Dicklesworthstone",
        "include_forks": True,
        "repos": [
            {
                "name": name,
                "html_url": f"https://github.com/Dicklesworthstone/{name}",
                "clone_url": f"https://github.com/Dicklesworthstone/{name}.git",
                "default_branch": "main",
                "language": "Python",
                "description": f"demo {name}",
                "size_kb": size_kb,
                "pushed_at": "2026-08-01T00:00:00Z",
                "fork": False,
                "archived": False,
                "topics": [],
            }
            for name, size_kb in sizes.items()
        ],
    }


def _inventory() -> list[dict]:
    return [
        {
            "name": "alpha",
            "primary_language": "Python",
            "languages": {".py": 1375},
            "total_loc": 1375,
            "size_kb": 4321,
            "file_count": 18,
            "readme_title": "alpha",
            "readme_summary": "summary alpha",
            "manifests": {"pyproject.toml": "pyproject.toml"},
            "entry_points": [],
            "has_tests": True,
            "test_cmd": "pytest -q",
            "auto_cmds": {"test": "pytest -q"},
            "last_commit_sha": "a" * 40,
            "last_commit_date": "2026-01-01T00:00:00Z",
            "last_commit_message": "init alpha",
        },
        {
            "name": "beta",
            "primary_language": "TypeScript",
            "languages": {".ts": 52340},
            "total_loc": 52340,
            "size_kb": 18750,
            "file_count": 220,
            "readme_title": "beta",
            "readme_summary": "summary beta",
            "manifests": {},
            "entry_points": [],
            "has_tests": False,
            "test_cmd": None,
            "auto_cmds": {},
            "last_commit_sha": "b" * 40,
            "last_commit_date": "",
            "last_commit_message": "init beta",
        },
        {
            "name": "gamma",
            "primary_language": "Python",
            "languages": {".py": 210},
            "total_loc": 210,
            "size_kb": 640,
            "file_count": 6,
            "readme_title": "gamma",
            "readme_summary": "summary gamma",
            "manifests": {},
            "entry_points": [],
            "has_tests": False,
            "test_cmd": None,
            "auto_cmds": {},
            "last_commit_sha": "c" * 40,
            "last_commit_date": "2025-06-15T12:00:00Z",
            "last_commit_message": "init gamma",
        },
    ]


def _is_real_png(path: Path) -> bool:
    """Assert-level check: exists, non-trivial size, real PNG magic bytes."""
    assert path.is_file(), path
    assert path.stat().st_size > 1000, (path, path.stat().st_size)
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", path
    return True


def test_figure_filenames_are_exactly_the_manuscript_four() -> None:
    assert FIGURE_FILENAMES == frozenset(
        {
            "fig_state_distribution.png",
            "fig_language_distribution.png",
            "fig_loc_size.png",
            "fig_staleness.png",
        }
    )


def test_state_distribution_figure_writes_real_png(tmp_path: Path) -> None:
    out = build_state_distribution_figure(_statuses(), tmp_path / "state.png")
    assert out == tmp_path / "state.png"
    _is_real_png(out)


def test_state_distribution_empty_statuses_raise_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_state_distribution_figure([], tmp_path / "empty.png")


def test_language_distribution_figure_maps_blank_language_to_other(
    tmp_path: Path,
) -> None:
    out = build_language_distribution_figure(_repos(), tmp_path / "lang.png")
    _is_real_png(out)


def test_loc_size_figure_writes_real_png(tmp_path: Path) -> None:
    out = build_loc_size_figure(_inventory(), tmp_path / "loc.png")
    _is_real_png(out)


def test_staleness_figure_skips_empty_dates_and_marks_median_max(
    tmp_path: Path,
) -> None:
    out = build_staleness_figure(_inventory(), tmp_path / "stale.png", now=NOW)
    _is_real_png(out)


def test_each_builder_is_byte_deterministic(tmp_path: Path) -> None:
    """Same inputs rendered twice produce byte-identical PNG files."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_runs = [
        build_state_distribution_figure(_statuses(), first / "state.png"),
        build_language_distribution_figure(_repos(), first / "lang.png"),
        build_loc_size_figure(_inventory(), first / "loc.png"),
        build_staleness_figure(_inventory(), first / "stale.png", now=NOW),
    ]
    second_runs = [
        build_state_distribution_figure(_statuses(), second / "state.png"),
        build_language_distribution_figure(_repos(), second / "lang.png"),
        build_loc_size_figure(_inventory(), second / "loc.png"),
        build_staleness_figure(_inventory(), second / "stale.png", now=NOW),
    ]
    for one, two in zip(first_runs, second_runs):
        assert one.read_bytes() == two.read_bytes(), one.name


def test_state_figure_is_input_order_independent(tmp_path: Path) -> None:
    """Sorting is internal: shuffling the input list must not change bytes."""
    shuffled = list(reversed(_statuses()))
    a = build_state_distribution_figure(_statuses(), tmp_path / "a.png")
    b = build_state_distribution_figure(shuffled, tmp_path / "b.png")
    assert a.read_bytes() == b.read_bytes()


def test_build_all_figures_writes_all_four(tmp_path: Path) -> None:
    inventory = {"generated_at": "2026-08-02T00:00:00Z", "repos": _inventory()}
    upstream = {
        "generated_at": "2026-08-02T00:00:00Z",
        "checked": 4,
        "ok": 2,
        "repos": _statuses(),
    }
    written = build_all_figures(_registry(), upstream, inventory, tmp_path / "figs")
    out_dir = tmp_path / "figs"
    assert out_dir.is_dir()
    assert {p.name for p in written} == set(FIGURE_FILENAMES)
    assert {p.name for p in out_dir.iterdir()} == set(FIGURE_FILENAMES)
    for path in written:
        _is_real_png(path)


def test_build_all_figures_joins_registry_size_kb_into_scatter(
    tmp_path: Path,
) -> None:
    """Inventory rows lacking size_kb are enriched from the registry twin."""
    inventory = {
        "generated_at": "2026-08-02T00:00:00Z",
        "repos": [
            {k: v for k, v in row.items() if k != "size_kb"} for row in _inventory()
        ],
    }
    upstream = {
        "generated_at": "2026-08-02T00:00:00Z",
        "checked": 4,
        "ok": 2,
        "repos": _statuses(),
    }
    written = build_all_figures(_registry(), upstream, inventory, tmp_path)
    scatter = next(p for p in written if p.name == "fig_loc_size.png")
    _is_real_png(scatter)
