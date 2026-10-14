from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src import git_probe
from src.git_probe import run_git
from src.inventory import build_inventory


def test_relative_checkout_preserves_commit_identity(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "corpus" / "repo"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "--allow-empty", "-qm", "fixture"], check=True, capture_output=True)
    monkeypatch.chdir(tmp_path)
    absolute = run_git(root, ["rev-parse", "--verify", "HEAD"])

    relative = run_git(Path("corpus/repo"), ["rev-parse", "--verify", "HEAD"])

    assert relative.returncode == 0
    assert relative.stdout == absolute.stdout
    assert build_inventory(["repo"], Path("corpus"))["repos"][0]["last_commit_sha"] == absolute.stdout.strip()


def test_real_slow_git_returns_timeout_outcome(tmp_path: Path, monkeypatch) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    executable = tmp_path / "bin" / "git"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nexec /bin/sleep 2\n")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(executable.parent))
    monkeypatch.setattr(git_probe, "DEFAULT_TIMEOUT_SECONDS", 0.05)

    result = run_git(tmp_path, ["rev-parse", "--verify", "HEAD"])

    assert result.returncode == 124
    assert result.stdout == ""
    assert "timed out" in result.stderr


@pytest.mark.parametrize("relative", [False, True])
def test_linked_worktree_preserves_commit_identity(tmp_path: Path, monkeypatch, relative: bool) -> None:
    root = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "--allow-empty", "-qm", "fixture"], check=True, capture_output=True)
    linked = tmp_path / "linked"
    subprocess.run(["git", "-C", str(root), "worktree", "add", "--detach", str(linked), "HEAD"], check=True, capture_output=True)
    expected = run_git(root, ["rev-parse", "--verify", "HEAD"])
    monkeypatch.chdir(tmp_path)

    result = run_git(Path("linked") if relative else linked, ["rev-parse", "--verify", "HEAD"])

    assert (linked / ".git").is_file()
    assert result.returncode == 0 and result.stdout == expected.stdout


def test_plain_child_does_not_borrow_ancestor(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    child = tmp_path / "plain"
    child.mkdir()

    result = run_git(child, ["rev-parse", "--git-dir"])

    assert result.returncode == 1
    assert result.stdout == ""


def test_probe_ignores_borrowed_environment(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "target"
    other = tmp_path / "other"
    for root in (target, other):
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_COMMON_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / "unrelated-index"))

    result = run_git(target, ["rev-parse", "--git-dir"])

    assert Path(result.stdout.strip()) == target / ".git"
    assert not (other / "unrelated-index").exists()
