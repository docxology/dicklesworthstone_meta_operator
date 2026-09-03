"""Project root and standard directory resolution.

Single source of truth for where artifacts live. ``output/`` is disposable
generated content; ``repos/`` holds fleet clones and is never tracked.
"""

from __future__ import annotations

from pathlib import Path

REPO_REGISTRY = "repo_registry.json"
UPSTREAM_STATUS = "upstream_status.json"
INVENTORY = "inventory.json"
HEALTH_GATE = "health_gate.json"
CORPUS_CATALOG = "corpus_catalog.md"
DASHBOARD = "dashboard.html"
RUNS_DIRNAME = "runs"


def resolve_project_root() -> Path:
    """Project root: parent of the ``src/`` directory containing this file."""
    return Path(__file__).resolve().parent.parent


def data_dir(project_root: Path | None = None) -> Path:
    return (project_root or resolve_project_root()) / "output" / "data"


def reports_dir(project_root: Path | None = None) -> Path:
    return (project_root or resolve_project_root()) / "output" / "reports"


def web_dir(project_root: Path | None = None) -> Path:
    return (project_root or resolve_project_root()) / "output" / "web"


def runs_dir(project_root: Path | None = None) -> Path:
    return data_dir(project_root) / RUNS_DIRNAME


def output_dirs(project_root: Path | None = None) -> dict[str, Path]:
    """Standard output directory map: data, reports, web, runs."""
    root = project_root or resolve_project_root()
    return {
        "data": data_dir(root),
        "reports": reports_dir(root),
        "web": web_dir(root),
        "runs": runs_dir(root),
    }


def repos_dir(project_root: Path | None = None) -> Path:
    return (project_root or resolve_project_root()) / "repos"


def ensure_output_dirs(project_root: Path | None = None) -> dict[str, Path]:
    """Create (idempotently) the standard output directories and return them."""
    dirs = output_dirs(project_root)
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs
