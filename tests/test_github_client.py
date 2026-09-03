"""Tests for ``src/github_client.py`` — fully offline.

The default-runner path is exercised through a PATH-stubbed fake ``gh`` shell
script (real subprocess, zero mocks, zero network). ``parse_repos`` is unit
tested against realistic GitHub API fixture dicts.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from src.github_client import GH_INSTALL_HINT, enumerate_repos, parse_repos, repos_api_url


def _repo_dict(
    name: str,
    *,
    fork: bool = False,
    language: str | None = "Python",
    topics: list[str] | None = ["cli"],
    description: str | None = "A repo",
    default_branch: str = "main",
) -> dict:
    """One realistic GitHub repos-list JSON object."""
    return {
        "name": name,
        "html_url": f"https://github.com/Dicklesworthstone/{name}",
        "clone_url": f"https://github.com/Dicklesworthstone/{name}.git",
        "default_branch": default_branch,
        "language": language,
        "description": description,
        "size": 2048,
        "pushed_at": "2026-08-30T12:00:00Z",
        "fork": fork,
        "archived": False,
        "topics": topics,
    }


PAGE1 = [_repo_dict("zeta_tool"), _repo_dict("alpha_lib", language=None, topics=None)]
PAGE2 = [
    _repo_dict("mirror_proj", fork=True, description="spiegel — ünïcode ✓"),
    _repo_dict("empty_repo", default_branch=None, description=None),
]


def _write_fake_gh(directory, body: str) -> None:
    """Write an executable fake ``gh`` script into ``directory``."""
    script = directory / "gh"
    script.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    script.chmod(0o755)


def test_repos_api_url():
    assert repos_api_url("Dicklesworthstone") == (
        "https://api.github.com/users/Dicklesworthstone/repos?per_page=100"
    )


def test_parse_repos_maps_fields_and_sorts():
    metas = parse_repos(PAGE1 + PAGE2)
    assert [m.name for m in metas] == ["alpha_lib", "empty_repo", "mirror_proj", "zeta_tool"]
    alpha = metas[0]
    assert alpha.language == ""  # None -> ""
    assert alpha.description == "A repo"
    assert alpha.topics == []  # None topics -> []
    empty = metas[1]
    assert empty.default_branch == ""
    assert empty.description == ""
    mirror = metas[2]
    assert mirror.fork is True
    assert empty.topics == ["cli"]  # default topics survive
    assert mirror.size_kb == 2048
    assert mirror.pushed_at == "2026-08-30T12:00:00Z"


def test_parse_repos_tolerates_missing_topics_key():
    raw = _repo_dict("no_topics")
    del raw["topics"]
    (meta,) = parse_repos([raw])
    assert meta.topics == []


@pytest.mark.parametrize("bad", [{"name": "x"}, "nope", None, 42])
def test_parse_repos_rejects_non_list(bad):
    with pytest.raises(ValueError, match="list"):
        parse_repos(bad)


def test_parse_repos_rejects_non_dict_entries():
    with pytest.raises(ValueError, match="index 1"):
        parse_repos([_repo_dict("ok"), "not-a-dict"])


def test_enumerate_repos_accepts_slurped_pages():
    seen_argv = []

    def runner(argv):
        seen_argv.append(argv)
        return json.dumps([PAGE1, PAGE2])

    metas = enumerate_repos("Dicklesworthstone", runner=runner)
    assert [m.name for m in metas] == ["alpha_lib", "empty_repo", "mirror_proj", "zeta_tool"]
    assert seen_argv == [
        ["gh", "api", repos_api_url("Dicklesworthstone"), "--paginate", "--slurp"]
    ]


def test_enumerate_repos_accepts_flat_list():
    metas = enumerate_repos("someone", runner=lambda _argv: json.dumps(PAGE1))
    assert [m.name for m in metas] == ["alpha_lib", "zeta_tool"]


def test_enumerate_repos_filters_forks_when_asked():
    metas = enumerate_repos(
        "someone", include_forks=False, runner=lambda _argv: json.dumps([PAGE1, PAGE2])
    )
    assert [m.name for m in metas] == ["alpha_lib", "empty_repo", "zeta_tool"]
    assert all(not m.fork for m in metas)


def test_default_runner_handles_slurped_pages_via_fake_gh(tmp_path, monkeypatch):
    _write_fake_gh(tmp_path, f"cat <<'JSON'\n{json.dumps([PAGE1, PAGE2], indent=1)}\nJSON\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    metas = enumerate_repos("Dicklesworthstone")
    assert [m.name for m in metas] == ["alpha_lib", "empty_repo", "mirror_proj", "zeta_tool"]


def test_default_runner_handles_legacy_concatenated_pages_via_fake_gh(tmp_path, monkeypatch):
    """Older gh --paginate emits per-page results back-to-back without --slurp."""
    _write_fake_gh(
        tmp_path,
        f"cat <<'JSON'\n{json.dumps(PAGE1)}\n{json.dumps(PAGE2)}\nJSON\n",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    metas = enumerate_repos("Dicklesworthstone")
    assert [m.name for m in metas] == ["alpha_lib", "empty_repo", "mirror_proj", "zeta_tool"]


def test_default_runner_surfaces_gh_failure(tmp_path, monkeypatch):
    _write_fake_gh(tmp_path, 'echo "rate limit exceeded" >&2\nexit 2\n')
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    with pytest.raises(RuntimeError, match="rate limit exceeded"):
        enumerate_repos("Dicklesworthstone")


def test_default_runner_gives_install_hint_when_gh_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "does-not-exist"))
    with pytest.raises(RuntimeError, match="gh CLI not found"):
        enumerate_repos("Dicklesworthstone")


def test_fake_gh_is_a_real_executable(tmp_path):
    """Sanity: the stub really runs as a subprocess (not a python-level fake)."""
    _write_fake_gh(tmp_path, "echo hi\n")
    proc = subprocess.run([str(tmp_path / "gh")], capture_output=True, text=True, check=True)
    assert proc.stdout.strip() == "hi"