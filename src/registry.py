"""Build, save, and load the repo registry (``output/data/repo_registry.json``).

The registry is the canonical in-memory + on-disk snapshot of the GitHub
corpus. Artifact shape (cross-builder contract):

``{"generated_at": <ISO8601Z>, "github_user": str, "include_forks": bool,
"repos": [RepoMeta.to_dict()...]}``

"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.models import RepoMeta, from_dict, to_dict
from src.project_paths import REPO_REGISTRY, data_dir
from src.jsonio import read_json as _read_json
from src.jsonio import write_json as _write_json


logger = logging.getLogger(__name__)

#: Re-export of the canonical registry artifact filename.
REGISTRY_FILENAME: str = REPO_REGISTRY




def build_registry(
    metas: list[RepoMeta],
    *,
    github_user: str,
    include_forks: bool,
    generated_at: str | None = None,
) -> dict:
    """Build the registry artifact dict in the exact cross-builder shape."""
    ordered = sorted(metas, key=lambda meta: meta.name)
    return {
        "generated_at": generated_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "github_user": github_user,
        "include_forks": include_forks,
        "repos": [to_dict(meta) for meta in ordered],
    }


def save_registry(registry: dict, project_root: Path) -> Path:
    """Write the registry to ``<project_root>/output/data/repo_registry.json``."""
    path = data_dir(project_root) / REGISTRY_FILENAME
    _write_json(path, registry)
    logger.info("saved registry with %d repos to %s", len(registry.get("repos", [])), path)
    return path


def load_registry(project_root: Path) -> dict:
    """Load the registry artifact; missing file raises ``FileNotFoundError``."""
    path = data_dir(project_root) / REGISTRY_FILENAME
    return _read_json(path, required=True)


def registry_names(registry: dict) -> list[str]:
    """Sorted repo names recorded in the registry."""
    return sorted(str(entry["name"]) for entry in registry.get("repos", []))


def registry_metas(registry: dict) -> dict[str, RepoMeta]:
    """Registry repos reconstructed as :class:`RepoMeta`, keyed by name."""
    metas: dict[str, RepoMeta] = {}
    for entry in registry.get("repos", []):
        meta = from_dict(RepoMeta, entry)
        metas[meta.name] = meta
    return metas