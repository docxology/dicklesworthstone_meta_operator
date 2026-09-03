"""Tests for src/inventory.py — real fixture repos in tmp_path, real git.

No mocks: every profile is computed against real files and real ``git``
subprocess calls against fixture repos constructed here.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from src.inventory import (
    LINE_LIMIT_PER_FILE,
    SOURCE_EXTENSIONS,
    build_inventory,
    profile_repo,
)
from src.models import to_dict


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.com",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.com",
            "GIT_AUTHOR_DATE": "2026-01-15T10:00:00+00:00",
            "GIT_COMMITTER_DATE": "2026-01-15T10:00:00+00:00",
            "HOME": str(repo),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin",
        },
    )


def _init_git_repo(repo: Path, message: str = "initial commit") -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _make_rust_py_repo(repo: Path) -> None:
    _write(repo / "src" / "lib.rs", "fn a() {}\nfn b() {}\nfn c() {}\n")  # 3 lines
    _write(repo / "src" / "main.py", "x = 1\ny = 2\nz = 3\nw = 4\nv = 5\n")  # 5 lines
    # .venv content must be skipped entirely.
    _write(repo / ".venv" / "ignored.py", "ignored = True\n" * 100)
    # Lockfile present but never counted.
    _write(repo / "uv.lock", "[package]\nname = \"x\"\n")
    # Unknown extension: counted under its own ext.
    _write(repo / "data.foo", "one\ntwo\nthree\nfour\n")  # 4 lines


def test_extension_map_covers_spec_exemplars() -> None:
    assert SOURCE_EXTENSIONS[".rs"] == "Rust"
    assert SOURCE_EXTENSIONS[".py"] == "Python"
    assert SOURCE_EXTENSIONS[".tsx"] == "TypeScript"
    assert SOURCE_EXTENSIONS[".mjs"] == "JavaScript"
    assert SOURCE_EXTENSIONS[".cc"] == "C++"
    assert SOURCE_EXTENSIONS[".zsh"] == "Shell"
    assert SOURCE_EXTENSIONS[".scss"] == "CSS"
    assert SOURCE_EXTENSIONS[".lean"] == "Lean"
    assert SOURCE_EXTENSIONS[".ipynb"] == "Jupyter Notebook"
    assert SOURCE_EXTENSIONS[".sol"] == "Solidity"
    # All keys lowercase with a leading dot.
    for ext, lang in SOURCE_EXTENSIONS.items():
        assert ext == ext.lower() and ext.startswith(".") and lang


def test_profile_counts_sources_and_skips(tmp_path: Path) -> None:
    repo = tmp_path / "demo"
    _make_rust_py_repo(repo)
    profile = profile_repo(repo, "demo")
    assert profile.languages == {".foo": 4, ".py": 5, ".rs": 3}
    assert profile.total_loc == 12
    assert profile.file_count == 3  # .venv file and uv.lock excluded
    assert profile.primary_language == "Python"  # max lines: .py (5) beats .rs (3)
    assert profile.name == "demo"


def test_primary_language_tie_breaks_alphabetically(tmp_path: Path) -> None:
    repo = tmp_path / "tie"
    _write(repo / "a.go", "package main\n")  # 1 line Go
    _write(repo / "b.py", "x = 1\n")  # 1 line Python
    profile = profile_repo(repo, "tie")
    assert profile.primary_language == "Go"


def test_primary_language_empty_repo(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    profile = profile_repo(repo, "empty")
    assert profile.primary_language == ""
    assert profile.languages == {}
    assert profile.total_loc == 0
    assert profile.file_count == 0


def test_line_limit_caps_oversized_file(tmp_path: Path) -> None:
    repo = tmp_path / "big"
    body = "\n" * LINE_LIMIT_PER_FILE  # 20001 lines total
    _write(repo / "generated.py", "x = 0\n" + body)
    profile = profile_repo(repo, "big")
    assert profile.languages[".py"] == LINE_LIMIT_PER_FILE
    assert profile.total_loc == LINE_LIMIT_PER_FILE


def test_last_commit_real_git(tmp_path: Path) -> None:
    repo = tmp_path / "committed"
    _write(repo / "README.md", "# Committed\n")
    _init_git_repo(repo, "fixture subject line")
    profile = profile_repo(repo, "committed")
    assert len(profile.last_commit_sha) == 40
    int(profile.last_commit_sha, 16)  # hex
    assert profile.last_commit_date.startswith("2026-01-15T10:00:00")
    assert profile.last_commit_message == "fixture subject line"


def test_last_commit_unborn_and_nongit(tmp_path: Path) -> None:
    unborn = tmp_path / "unborn"
    unborn.mkdir()
    _git(unborn, "init", "-q")
    profile = profile_repo(unborn, "unborn")
    assert (profile.last_commit_sha, profile.last_commit_date, profile.last_commit_message) == (
        "",
        "",
        "",
    )
    plain = tmp_path / "plain"
    plain.mkdir()
    profile2 = profile_repo(plain, "plain")
    assert (profile2.last_commit_sha, profile2.last_commit_date, profile2.last_commit_message) == (
        "",
        "",
        "",
    )


def test_readme_title_and_summary(tmp_path: Path) -> None:
    repo = tmp_path / "docs"
    paragraph = " ".join(["word"] * 12)  # > 40 chars
    _write(
        repo / "README.md",
        f"# Fancy Tool\n\nSome intro.\n\n{paragraph}\n\nClosing note.\n",
    )
    profile = profile_repo(repo, "docs")
    assert profile.readme_title == "Fancy Tool"
    assert profile.readme_summary == paragraph


def test_readme_summary_truncation(tmp_path: Path) -> None:
    repo = tmp_path / "long"
    long_paragraph = "x" * 400
    _write(repo / "README.md", f"# Long\n\n{long_paragraph}\n")
    profile = profile_repo(repo, "long")
    assert profile.readme_summary == "x" * 280 + "…"


def test_readme_variants(tmp_path: Path) -> None:
    # No title line.
    repo = tmp_path / "notitle"
    _write(
        repo / "README.md", "Just a paragraph that is definitely long enough here.\n\nBody.\n"
    )
    profile = profile_repo(repo, "notitle")
    assert profile.readme_title == ""
    assert profile.readme_summary.startswith("Just a paragraph")
    # Empty readme.
    repo2 = tmp_path / "emptyreadme"
    _write(repo2 / "README.md", "\n\n")
    profile2 = profile_repo(repo2, "emptyreadme")
    assert profile2.readme_title == "" and profile2.readme_summary == ""
    # Missing readme.
    repo3 = tmp_path / "noreadme"
    repo3.mkdir()
    profile3 = profile_repo(repo3, "noreadme")
    assert profile3.readme_title == "" and profile3.readme_summary == ""
    # Case-insensitive: lowercase readme.md in repo root.
    repo4 = tmp_path / "lowercase"
    _write(repo4 / "readme.md", "# Lower Name\n\n" + "y" * 60 + "\n")
    profile4 = profile_repo(repo4, "lowercase")
    assert profile4.readme_title == "Lower Name"


def test_manifests_and_entry_points(tmp_path: Path) -> None:
    repo = tmp_path / "full"
    _write(repo / "Cargo.toml", "[package]\nname = \"x\"\n")
    _write(repo / "pyproject.toml", "[project]\nname = \"x\"\n")
    _write(repo / "tsconfig.json", "{}\n")
    _write(repo / "src" / "lib.rs", "fn main() {}\n")
    _write(repo / "cli.py", "print(1)\n")
    _write(repo / "cmd" / "toolone" / "main.go", "package main\n")
    _write(repo / "cmd" / "tooltwo" / "main.go", "package main\n")
    _write(repo / "cmd" / "toolthree" / "helper.go", "package main\n")
    _write(repo / ".github" / "workflows" / "ci.yml", "on: push\n")
    profile = profile_repo(repo, "full")
    assert profile.manifests == {
        "pyproject.toml": "pyproject.toml",
        "Cargo.toml": "Cargo.toml",
        "tsconfig.json": "tsconfig.json",
        ".github/workflows": ".github/workflows",
    }
    assert profile.entry_points == [
        "cli.py",
        "cmd/toolone/main.go",
        "cmd/tooltwo/main.go",
        "src/lib.rs",
    ]


def test_entry_point_cap(tmp_path: Path) -> None:
    repo = tmp_path / "capped"
    for i in range(20):
        _write(repo / "cmd" / f"tool{i:02d}" / "main.go", "package main\n")
    profile = profile_repo(repo, "capped")
    assert len(profile.entry_points) == 12
    assert profile.entry_points == sorted(profile.entry_points)


def test_cargo_precedence(tmp_path: Path) -> None:
    repo = tmp_path / "both"
    _write(repo / "Cargo.toml", "[package]\nname = \"x\"\n")
    _write(repo / "pyproject.toml", "[project]\nname = \"x\"\n[tool.ruff]\n")
    profile = profile_repo(repo, "both")
    assert profile.auto_cmds == {
        "test": "cargo test",
        "lint": "cargo clippy -- -D warnings",
        "typecheck": "cargo check",
    }
    assert profile.has_tests is True
    assert profile.test_cmd == "cargo test"


def test_pyproject_commands(tmp_path: Path) -> None:
    with_ruff = tmp_path / "ruffproj"
    _write(
        with_ruff / "pyproject.toml",
        "[project]\nname = \"x\"\n[dependency-groups]\ndev = [\"pytest\", \"ruff\", \"mypy\"]\n",
    )
    profile = profile_repo(with_ruff, "ruffproj")
    assert profile.auto_cmds == {
        "test": "uv run pytest",
        "lint": "uv run ruff check .",
        "typecheck": "uv run mypy .",
    }
    without = tmp_path / "plainproj"
    _write(without / "pyproject.toml", "[project]\nname = \"x\"\n")
    profile2 = profile_repo(without, "plainproj")
    assert profile2.auto_cmds == {"test": "uv run python -m pytest"}
    assert profile2.has_tests is True


def test_pyproject_without_pytest_dependency(tmp_path: Path) -> None:
    repo = tmp_path / "nopytest"
    _write(repo / "pyproject.toml", "[project]\nname = \"x\"\n")
    profile = profile_repo(repo, "nopytest")
    assert profile.test_cmd == "uv run python -m pytest"


def test_package_json_scripts(tmp_path: Path) -> None:
    repo = tmp_path / "npmfull"
    _write(
        repo / "package.json",
        json.dumps(
            {
                "scripts": {"test": "vitest", "lint": "eslint .", "typecheck": "tsc"},
            }
        ),
    )
    profile = profile_repo(repo, "npmfull")
    assert profile.auto_cmds == {
        "test": "npm test",
        "lint": "npm run lint",
        "typecheck": "npm run typecheck",
    }
    # typescript dep, no typecheck script -> npx fallback.
    repo2 = tmp_path / "npmts"
    _write(
        repo2 / "package.json",
        json.dumps(
            {
                "scripts": {"test": "jest"},
                "devDependencies": {"typescript": "^5.0.0"},
            }
        ),
    )
    profile2 = profile_repo(repo2, "npmts")
    assert profile2.auto_cmds == {"test": "npm test", "typecheck": "npx tsc --noEmit"}
    # No test script at all.
    repo3 = tmp_path / "npmno"
    _write(repo3 / "package.json", json.dumps({"scripts": {"build": "tsc"}}))
    profile3 = profile_repo(repo3, "npmno")
    assert profile3.has_tests is False
    assert profile3.test_cmd is None
    assert profile3.auto_cmds == {}


def test_go_and_makefile_commands(tmp_path: Path) -> None:
    gomod = tmp_path / "goproj"
    _write(gomod / "go.mod", "module example.com/x\n\ngo 1.22\n")
    profile = profile_repo(gomod, "goproj")
    assert profile.auto_cmds == {"test": "go test ./...", "lint": "go vet ./..."}
    make = tmp_path / "makeproj"
    _write(make / "Makefile", "PREFIX ?= /usr\n\n.PHONY: test\n\ntest:\n\tgo test ./...\n")
    profile2 = profile_repo(make, "makeproj")
    assert profile2.auto_cmds == {"test": "make test"}
    # Makefile without a test target yields nothing.
    make2 = tmp_path / "makeno"
    _write(make2 / "Makefile", "all:\n\ttrue\n")
    profile3 = profile_repo(make2, "makeno")
    assert profile3.auto_cmds == {} and profile3.test_cmd is None


def test_auto_cmd_keys_constrained(tmp_path: Path) -> None:
    repo = tmp_path / "keys"
    _write(repo / "pyproject.toml", "[project]\nname = \"x\"\n[tool.ruff]\n")
    profile = profile_repo(repo, "keys")
    assert set(profile.auto_cmds) <= {"test", "lint", "typecheck"}


def test_build_inventory_repos_and_missing(tmp_path: Path) -> None:
    repos_dir = tmp_path / "repos"
    _make_rust_py_repo(repos_dir / "present")
    _write(repos_dir / "present" / "README.md", "# Present\n\n" + "z" * 50 + "\n")
    (repos_dir / "also_present").mkdir(parents=True)
    _write(repos_dir / "also_present" / "app.py", "run()\n")
    inventory = build_inventory(
        ["present", "absent", "also_present", "present"],
        repos_dir,
        generated_at="2026-09-02T00:00:00Z",
    )
    assert inventory["generated_at"] == "2026-09-02T00:00:00Z"
    assert [r["name"] for r in inventory["repos"]] == ["also_present", "present"]
    assert inventory["missing"] == ["absent"]
    present = next(r for r in inventory["repos"] if r["name"] == "present")
    assert present["primary_language"] == "Python"
    assert present["readme_title"] == "Present"
    assert present["has_tests"] is False and present["test_cmd"] is None
    # Deterministic: identical inputs give identical output.
    again = build_inventory(
        ["present", "also_present", "absent"],
        repos_dir,
        generated_at="2026-09-02T00:00:00Z",
    )
    assert inventory == again


def test_build_inventory_generated_at_defaults(tmp_path: Path) -> None:
    repos_dir = tmp_path / "repos"
    (repos_dir / "x").mkdir(parents=True)
    inventory = build_inventory(["x"], repos_dir)
    assert inventory["generated_at"].endswith("Z")
    assert len(inventory["generated_at"]) == 20
    assert inventory["missing"] == []


def test_profile_to_dict_shape(tmp_path: Path) -> None:
    repo = tmp_path / "shape"
    _make_rust_py_repo(repo)
    _write(repo / "Cargo.toml", "[package]\nname = \"x\"\n")
    _init_git_repo(repo, "shape commit")
    entry = to_dict(profile_repo(repo, "shape"))
    expected_keys = {
        "name",
        "primary_language",
        "languages",
        "total_loc",
        "file_count",
        "readme_title",
        "readme_summary",
        "manifests",
        "entry_points",
        "has_tests",
        "test_cmd",
        "auto_cmds",
        "last_commit_sha",
        "last_commit_date",
        "last_commit_message",
    }
    assert set(entry) == expected_keys
    # JSON-serializable as-is.
    json.dumps(entry)
