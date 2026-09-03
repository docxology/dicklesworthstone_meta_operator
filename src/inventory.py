"""Per-repo interpretability profiles and the corpus inventory artifact.

Pure-local module: reads real files under a clone, runs ``git log`` in it, and
never touches the network. ``profile_repo`` builds one :class:`RepoProfile`;
``build_inventory`` fans it over a repos directory and returns the
``inventory.json`` payload shape (repos sorted by name, plus a ``missing``
list for registry names with no local clone).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.models import AUTO_COMMAND_KEYS, RepoProfile, to_dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extension -> language map (deterministic, lowercase, dot-prefixed keys)
# ---------------------------------------------------------------------------

SOURCE_EXTENSIONS: dict[str, str] = {
    ".rs": "Rust",
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".go": "Go",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cc": "C++",
    ".java": "Java",
    ".rb": "Ruby",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".fish": "Shell",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".md": "Markdown",
    ".tex": "TeX",
    ".lean": "Lean",
    ".sql": "SQL",
    ".r": "R",
    ".jl": "Julia",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".hs": "Haskell",
    ".ml": "OCaml",
    ".lua": "Lua",
    ".php": "PHP",
    ".pl": "Perl",
    ".vim": "Vim Script",
    ".el": "Emacs Lisp",
    ".clj": "Clojure",
    ".erl": "Erlang",
    ".ex": "Elixir",
    ".dart": "Dart",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".toml": "TOML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".nix": "Nix",
    ".zig": "Zig",
    ".sol": "Solidity",
    ".ipynb": "Jupyter Notebook",
}

# Directory names never traversed (build artifacts, tool caches, vendored code).
SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "target",
        "dist",
        "build",
        ".mypy_cache",
        ".ruff_cache",
        "htmlcov",
        ".tox",
        "site-packages",
        ".eggs",
        "vendor",
    }
)

# Lockfiles and other generated dependency pins: present but never counted.
SKIP_FILES: frozenset[str] = frozenset(
    {
        "uv.lock",
        "package-lock.json",
        "yarn.lock",
        "Cargo.lock",
        "poetry.lock",
        "pnpm-lock.yaml",
    }
)

# Documented guard against generated monsters: a file with more lines than
# this counts as exactly this many lines.
LINE_LIMIT_PER_FILE: int = 20000

README_CANDIDATES: tuple[str, ...] = ("README.md", "README.rst", "README.txt", "README")
README_SUMMARY_MIN_CHARS: int = 40
README_SUMMARY_MAX_CHARS: int = 280

MANIFEST_CANDIDATES: tuple[str, ...] = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "Cargo.toml",
    "package.json",
    "tsconfig.json",
    "go.mod",
    "go.sum",
    "Makefile",
    "CMakeLists.txt",
    "meson.build",
    "Gemfile",
    "mix.exs",
    "flake.nix",
    "deno.json",
    "Dockerfile",
    "docker-compose.yml",
    ".github/workflows",
)

ENTRY_POINT_CANDIDATES: tuple[str, ...] = (
    "src/main.rs",
    "src/lib.rs",
    "main.py",
    "__main__.py",
    "src/main.py",
    "src/__main__.py",
    "app.py",
    "server.py",
    "cli.py",
    "main.go",
    "index.js",
    "src/index.ts",
    "src/main.ts",
    "main.c",
    "main.cpp",
    "main.rb",
    "cmd",
)

ENTRY_POINT_CAP: int = 12

_UNKNOWN_LANGUAGE: str = "Other"


# ---------------------------------------------------------------------------
# Source counting
# ---------------------------------------------------------------------------


def _iter_repo_files(repo_path: Path) -> list[Path]:
    """All regular files under ``repo_path``, pruning SKIP_DIRS, sorted."""
    found: list[Path] = []
    stack: list[Path] = [repo_path]
    while stack:
        current = stack.pop()
        for child in sorted(current.iterdir(), key=lambda p: p.name):
            if child.is_dir():
                if child.name not in SKIP_DIRS:
                    stack.append(child)
            elif child.is_file() and child.name not in SKIP_FILES:
                found.append(child)
    found.sort()
    return found


def _count_lines(path: Path) -> int:
    """Line count of ``path``, binary-safe, capped at LINE_LIMIT_PER_FILE."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("inventory: unreadable file %s: %s", path, exc)
        return 0
    return min(len(text.splitlines()), LINE_LIMIT_PER_FILE)


def _count_sources(repo_path: Path) -> tuple[dict[str, int], int, int]:
    """Extension -> line count, total LOC, and counted file count."""
    languages: dict[str, int] = {}
    total_loc = 0
    file_count = 0
    for path in _iter_repo_files(repo_path):
        suffix = path.suffix.lower()
        if not suffix:
            # No extension: not a keyed source file; excluded from counting.
            continue
        lines = _count_lines(path)
        languages[suffix] = languages.get(suffix, 0) + lines
        total_loc += lines
        file_count += 1
    return dict(sorted(languages.items())), total_loc, file_count


def _primary_language(languages: dict[str, int]) -> str:
    """Language of the max-line extension; ties broken alphabetically."""
    if not languages:
        return ""
    max_lines = max(languages.values())
    candidates = sorted(
        (SOURCE_EXTENSIONS.get(ext, _UNKNOWN_LANGUAGE), ext)
        for ext, lines in languages.items()
        if lines == max_lines
    )
    return candidates[0][0]


# ---------------------------------------------------------------------------
# README interpretation
# ---------------------------------------------------------------------------


def _find_readme(repo_path: Path) -> Path | None:
    """Case-insensitive match of README_CANDIDATES in the repo root."""
    if not repo_path.is_dir():
        return None
    lowered = {child.name.lower(): child for child in repo_path.iterdir() if child.is_file()}
    for candidate in README_CANDIDATES:
        match = lowered.get(candidate.lower())
        if match is not None:
            return match
    return None


def _readme_summary(text: str) -> str:
    """First paragraph longer than 40 chars, collapsed, truncated to 280."""
    for paragraph in text.split("\n\n"):
        collapsed = " ".join(paragraph.split())
        if len(collapsed) > README_SUMMARY_MIN_CHARS:
            if len(collapsed) > README_SUMMARY_MAX_CHARS:
                return collapsed[:README_SUMMARY_MAX_CHARS] + "…"
            return collapsed
    return ""


def _readme(repo_path: Path) -> tuple[str, str]:
    """(title, summary) from the repo README; ("", "") when absent/empty."""
    readme = _find_readme(repo_path)
    if readme is None:
        return "", ""
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("inventory: unreadable README %s: %s", readme, exc)
        return "", ""
    if not text.strip():
        return "", ""
    title = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            break
    return title, _readme_summary(text)


# ---------------------------------------------------------------------------
# Manifests and entry points
# ---------------------------------------------------------------------------


def _detect_manifests(repo_path: Path) -> dict[str, str]:
    """Existing manifest candidates: candidate name -> repo-relative path."""
    manifests: dict[str, str] = {}
    for candidate in MANIFEST_CANDIDATES:
        if (repo_path / candidate).exists():
            manifests[candidate] = candidate
    return manifests


def _detect_entry_points(repo_path: Path) -> list[str]:
    """Existing entry-point candidates as sorted repo-relative paths, capped."""
    found: list[str] = []
    for candidate in ENTRY_POINT_CANDIDATES:
        if candidate == "cmd":
            cmd_dir = repo_path / "cmd"
            if cmd_dir.is_dir():
                for child in sorted(cmd_dir.iterdir(), key=lambda p: p.name):
                    if (child / "main.go").is_file():
                        found.append(f"cmd/{child.name}/main.go")
            continue
        if (repo_path / candidate).is_file():
            found.append(candidate)
    return sorted(found)[:ENTRY_POINT_CAP]


# ---------------------------------------------------------------------------
# Auto-detected commands
# ---------------------------------------------------------------------------


def _commands_from_cargo(repo_path: Path) -> dict[str, str]:
    return {
        "test": "cargo test",
        "lint": "cargo clippy -- -D warnings",
        "typecheck": "cargo check",
    }


def _commands_from_pyproject(repo_path: Path) -> dict[str, str]:
    text = (repo_path / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
    cmds: dict[str, str] = {
        "test": "uv run pytest" if "pytest" in text else "uv run python -m pytest"
    }
    if "ruff" in text:
        cmds["lint"] = "uv run ruff check ."
    if "mypy" in text:
        cmds["typecheck"] = "uv run mypy ."
    return cmds


def _commands_from_package_json(repo_path: Path) -> dict[str, str]:
    raw = (repo_path / "package.json").read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("inventory: invalid package.json in %s", repo_path)
        return {}
    if not isinstance(data, dict):
        return {}
    scripts = data.get("scripts") or {}
    if not isinstance(scripts, dict):
        scripts = {}
    cmds: dict[str, str] = {}
    if scripts.get("test"):
        cmds["test"] = "npm test"
    if scripts.get("lint"):
        cmds["lint"] = "npm run lint"
    if scripts.get("typecheck"):
        cmds["typecheck"] = "npm run typecheck"
    else:
        deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        if any("typescript" in f"{k} {v}" for k, v in deps.items()):
            cmds["typecheck"] = "npx tsc --noEmit"
    return cmds


def _commands_from_go_mod(repo_path: Path) -> dict[str, str]:
    return {"test": "go test ./...", "lint": "go vet ./..."}


def _commands_from_makefile(repo_path: Path) -> dict[str, str]:
    text = (repo_path / "Makefile").read_text(encoding="utf-8", errors="replace")
    if re.search(r"^test:", text, flags=re.MULTILINE):
        return {"test": "make test"}
    return {}


_PRECEDENCE: tuple[tuple[str, object], ...] = (
    ("Cargo.toml", _commands_from_cargo),
    ("pyproject.toml", _commands_from_pyproject),
    ("package.json", _commands_from_package_json),
    ("go.mod", _commands_from_go_mod),
    ("Makefile", _commands_from_makefile),
)


def _auto_cmds(repo_path: Path) -> dict[str, str]:
    """First manifest in precedence order that exists yields the commands."""
    for filename, builder in _PRECEDENCE:
        if (repo_path / filename).exists():
            cmds = {k: v for k, v in builder(repo_path).items() if k in AUTO_COMMAND_KEYS and v}
            if cmds:
                return cmds
    return {}


# ---------------------------------------------------------------------------
# Last commit
# ---------------------------------------------------------------------------


def _last_commit(repo_path: Path) -> tuple[str, str, str]:
    """(sha, committer-date-ISO8601, subject) of HEAD; ("", "", "") on failure."""
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%H%x00%cI%x00%s"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("inventory: git log failed in %s: %s", repo_path, exc)
        return "", "", ""
    if proc.returncode != 0 or not proc.stdout.strip():
        return "", "", ""
    parts = proc.stdout.strip().split("\x00", 2)
    if len(parts) != 3:
        return "", "", ""
    return parts[0], parts[1], parts[2]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def profile_repo(repo_path: Path, name: str) -> RepoProfile:
    """Build the interpretability profile of one local clone."""
    languages, total_loc, file_count = _count_sources(repo_path)
    readme_title, readme_summary = _readme(repo_path)
    auto_cmds = _auto_cmds(repo_path)
    sha, date, message = _last_commit(repo_path)
    return RepoProfile(
        name=name,
        primary_language=_primary_language(languages),
        languages=languages,
        total_loc=total_loc,
        file_count=file_count,
        readme_title=readme_title,
        readme_summary=readme_summary,
        manifests=_detect_manifests(repo_path),
        entry_points=_detect_entry_points(repo_path),
        has_tests="test" in auto_cmds,
        test_cmd=auto_cmds.get("test"),
        auto_cmds=auto_cmds,
        last_commit_sha=sha,
        last_commit_date=date,
        last_commit_message=message,
    )


def build_inventory(
    names: list[str], repos_dir: Path, *, generated_at: str | None = None
) -> dict:
    """Build the inventory artifact payload over the registry names.

    Names without a local clone under ``repos_dir`` are omitted from
    ``repos`` and recorded (sorted) under ``missing``.
    """
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    repos: list[dict] = []
    missing: list[str] = []
    for name in sorted(set(names)):
        repo_path = repos_dir / name
        if repo_path.is_dir():
            repos.append(to_dict(profile_repo(repo_path, name)))
        else:
            missing.append(name)
    repos.sort(key=lambda entry: entry["name"])
    return {"generated_at": stamp, "repos": repos, "missing": missing}
