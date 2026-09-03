"""Tests for the frozen contract modules: models, jsonio, config, project_paths.

Offline and filesystem-only: real temp files via ``tmp_path``, real YAML, real
atomic-write behavior. Zero mocks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import project_paths
from src.config import OperatorConfig, load_config
from src.jsonio import read_json, sha8, write_json, write_text
from src.models import (
    AUTO_COMMAND_KEYS,
    CLONE_STATUSES,
    UPSTREAM_OK_STATES,
    UPSTREAM_STATES,
    CloneOutcome,
    RepoMeta,
    from_dict,
    to_dict,
)


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


class TestModels:
    def _meta(self, name: str = "alpha") -> RepoMeta:
        return RepoMeta(
            name=name,
            html_url=f"https://github.com/Dicklesworthstone/{name}",
            clone_url=f"https://github.com/Dicklesworthstone/{name}.git",
            default_branch="main",
            language="Rust",
            description="d",
            size_kb=10,
            pushed_at="2026-01-01T00:00:00Z",
            fork=False,
            archived=False,
            topics=["t"],
        )

    def test_to_dict_recurses_through_dataclass_and_containers(self):
        outcome = CloneOutcome(name="a", status="cloned", dest="/tmp/a")
        payload = {"list": [outcome], "plain": 1, "tuple": (outcome,)}
        dumped = to_dict(payload)
        assert dumped["list"][0]["status"] == "cloned"
        assert dumped["tuple"][0]["name"] == "a"
        assert dumped["plain"] == 1

    def test_from_dict_roundtrip(self):
        meta = self._meta()
        assert from_dict(RepoMeta, to_dict(meta)) == meta

    def test_from_dict_rejects_non_dict(self):
        with pytest.raises(TypeError, match="expects a dict"):
            from_dict(RepoMeta, ["nope"])

    def test_from_dict_reports_missing_required_fields(self):
        raw = to_dict(self._meta())
        del raw["name"]
        del raw["clone_url"]
        with pytest.raises(ValueError, match="missing required fields"):
            from_dict(RepoMeta, raw)

    def test_from_dict_tolerates_absent_defaulted_fields(self):
        raw = to_dict(self._meta())
        del raw["topics"]
        meta = from_dict(RepoMeta, raw)
        assert meta.topics == []

    def test_vocabularies(self):
        assert CLONE_STATUSES == {"cloned", "already_cloned", "failed", "mismatch"}
        assert UPSTREAM_OK_STATES <= UPSTREAM_STATES
        assert UPSTREAM_OK_STATES == {"on_upstream", "unborn"}
        assert AUTO_COMMAND_KEYS == {"test", "lint", "typecheck"}
        assert "off_default" in UPSTREAM_STATES


# ---------------------------------------------------------------------------
# jsonio
# ---------------------------------------------------------------------------


class TestJsonio:
    def test_write_read_json_roundtrip(self, tmp_path: Path):
        path = tmp_path / "out" / "data.json"
        payload = {"b": 1, "a": ["x", "y"], "nested": {"k": "v"}}
        returned = write_json(path, payload)
        assert returned == path
        assert read_json(path) == payload
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n") and '\n  "a"' in text  # indent=2

    def test_write_json_is_atomic_no_tmp_litter(self, tmp_path: Path):
        path = tmp_path / "artifact.json"
        write_json(path, {"k": "v"})
        write_json(path, {"k": "v2"})
        assert read_json(path) == {"k": "v2"}
        assert [p.name for p in path.parent.iterdir()] == ["artifact.json"]

    def test_read_json_required_missing_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="required JSON artifact missing"):
            read_json(tmp_path / "absent.json", required=True)

    def test_read_json_optional_missing_returns_none(self, tmp_path: Path):
        assert read_json(tmp_path / "absent.json", required=False) is None

    def test_read_json_invalid_json_raises(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            read_json(path)

    def test_write_text(self, tmp_path: Path):
        path = tmp_path / "sub" / "report.md"
        write_text(path, "# hi\n")
        assert path.read_text(encoding="utf-8") == "# hi\n"

    def test_sha8_deterministic_and_short(self):
        assert sha8("hello") == sha8("hello")
        assert len(sha8("hello")) == 8
        assert sha8("hello") != sha8("hellp")


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


class TestConfig:
    def test_defaults_without_config_file(self, tmp_path: Path):
        config = load_config(tmp_path)
        assert config == OperatorConfig()

    def test_loads_overrides_from_real_yaml(self, tmp_path: Path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "operator_config.yaml").write_text(
            "github_user: someoneelse\nclone_workers: 3\ninclude_forks: false\n",
            encoding="utf-8",
        )
        config = load_config(tmp_path)
        assert config.github_user == "someoneelse"
        assert config.clone_workers == 3
        assert config.include_forks is False
        assert config.run_timeout_s == 600  # untouched default

    def test_unknown_key_rejected(self, tmp_path: Path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "operator_config.yaml").write_text(
            "clone_workerz: 3\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="Unknown config keys"):
            load_config(tmp_path)

    def test_non_mapping_config_rejected(self, tmp_path: Path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "operator_config.yaml").write_text(
            "- just\n- a list\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="must contain a YAML mapping"):
            load_config(tmp_path)

    def test_empty_config_file_yields_defaults(self, tmp_path: Path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "operator_config.yaml").write_text("", encoding="utf-8")
        assert load_config(tmp_path) == OperatorConfig()

    @pytest.mark.parametrize(
        "overrides, fragment",
        [
            ({"github_user": "org/name"}, "bare username"),
            ({"github_user": ""}, "bare username"),
            ({"repos_dir": "/absolute/path"}, "relative"),
            ({"clone_workers": 0}, "clone_workers"),
            ({"fetch_workers": -1}, "fetch_workers"),
            ({"run_workers": 0}, "run_workers"),
            ({"run_timeout_s": 0}, "run_timeout_s"),
            ({"stream_tail_bytes": 0}, "stream_tail_bytes"),
        ],
    )
    def test_validated_rejects_nonsense(self, overrides, fragment):
        config = OperatorConfig(**overrides)
        with pytest.raises(ValueError, match=fragment):
            config.validated()


# ---------------------------------------------------------------------------
# project_paths
# ---------------------------------------------------------------------------


class TestProjectPaths:
    def test_resolve_project_root_is_parent_of_src(self):
        assert project_paths.resolve_project_root().name == (
            "dicklesworthstone_meta_operator"
        )

    def test_output_dirs_and_ensure_idempotent(self, tmp_path: Path):
        dirs = project_paths.ensure_output_dirs(tmp_path)
        assert set(dirs) == {"data", "reports", "web", "runs"}
        assert dirs["runs"].parent == dirs["data"]
        for path in dirs.values():
            assert path.is_dir()
        again = project_paths.ensure_output_dirs(tmp_path)
        assert again == dirs

    def test_explicit_root_overrides_default(self, tmp_path: Path):
        assert project_paths.data_dir(tmp_path) == tmp_path / "output" / "data"
        assert project_paths.repos_dir(tmp_path) == tmp_path / "repos"

    def test_artifact_filename_constants(self):
        assert project_paths.REPO_REGISTRY == "repo_registry.json"
        assert project_paths.UPSTREAM_STATUS == "upstream_status.json"
        assert project_paths.INVENTORY == "inventory.json"
        assert project_paths.HEALTH_GATE == "health_gate.json"
        assert project_paths.CORPUS_CATALOG == "corpus_catalog.md"
        assert project_paths.DASHBOARD == "dashboard.html"
