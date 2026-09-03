"""Tests for ``src/registry.py`` — artifact shape, save/load round-trip.

Offline and filesystem-only: uses ``tmp_path`` project roots and the guarded
jsonio path inside ``registry.py`` (documented contract API or its faithful
fallback).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.models import RepoMeta, to_dict
from src.project_paths import REPO_REGISTRY
from src.registry import (
    REGISTRY_FILENAME,
    build_registry,
    load_registry,
    registry_metas,
    registry_names,
    save_registry,
)


def _meta(name: str, **overrides) -> RepoMeta:
    fields = {
        "name": name,
        "html_url": f"https://github.com/Dicklesworthstone/{name}",
        "clone_url": f"https://github.com/Dicklesworthstone/{name}.git",
        "default_branch": "main",
        "language": "Python",
        "description": f"repo {name}",
        "size_kb": 512,
        "pushed_at": "2026-09-01T00:00:00Z",
        "fork": False,
        "archived": False,
        "topics": ["cli"],
    }
    fields.update(overrides)
    return RepoMeta(**fields)


def test_registry_filename_reexport():
    assert REGISTRY_FILENAME == REPO_REGISTRY == "repo_registry.json"


def test_build_registry_shape_and_sorting():
    metas = [_meta("zeta"), _meta("alpha", topics=[], language=None, description=None)]
    registry = build_registry(
        metas, github_user="Dicklesworthstone", include_forks=False, generated_at="2026-09-02T00:00:00Z"
    )
    assert registry["generated_at"] == "2026-09-02T00:00:00Z"
    assert registry["github_user"] == "Dicklesworthstone"
    assert registry["include_forks"] is False
    assert [r["name"] for r in registry["repos"]] == ["alpha", "zeta"]


def test_build_registry_default_generated_at():
    registry = build_registry([], github_user="u", include_forks=True)
    assert registry["generated_at"].endswith("Z")
    assert "T" in registry["generated_at"]
    assert len(registry["generated_at"]) == 20  # %Y-%m-%dT%H:%M:%SZ


def test_save_load_roundtrip(tmp_path: Path):
    metas = [
        _meta("b_repo", topics=["one", "two"], description="ünïcode ✓"),
        _meta("a_repo", fork=True, default_branch="trunk", size_kb=0),
    ]
    registry = build_registry(
        metas, github_user="Dicklesworthstone", include_forks=True, generated_at="2026-09-02T00:00:00Z"
    )
    path = save_registry(registry, tmp_path)
    assert path == tmp_path / "output" / "data" / REPO_REGISTRY
    assert path.exists()

    loaded = load_registry(tmp_path)
    assert loaded == registry
    # The round-trip invariant: save -> load -> registry_metas yields identical
    # dataclasses to the originals.
    metas_by_name = registry_metas(loaded)
    assert set(metas_by_name) == {"a_repo", "b_repo"}
    for original in metas:
        assert metas_by_name[original.name] == original
    assert registry_names(loaded) == ["a_repo", "b_repo"]


def test_load_registry_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_registry(tmp_path)


def test_registry_metas_and_names_on_raw_artifact():
    registry = {
        "generated_at": "2026-09-02T00:00:00Z",
        "github_user": "u",
        "include_forks": False,
        "repos": [to_dict(_meta("second")), to_dict(_meta("first"))],
    }
    assert registry_names(registry) == ["first", "second"]
    metas = registry_metas(registry)
    assert metas["first"].clone_url == "https://github.com/Dicklesworthstone/first.git"
