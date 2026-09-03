"""Typed loader for ``data/operator_config.yaml``.

Config-only module (template precedent: ``experiment_config.py``): performs
one YAML read with typed defaults and strict validation. Unknown keys are a
configuration error, not a silent fallback.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_FILENAME = "operator_config.yaml"


@dataclass(frozen=True)
class OperatorConfig:
    """Runtime settings for the meta-operator."""

    github_user: str = "Dicklesworthstone"
    repos_dir: str = "repos"
    include_forks: bool = True
    clone_workers: int = 8
    fetch_workers: int = 8
    run_workers: int = 6
    run_timeout_s: int = 600
    stream_tail_bytes: int = 20000

    def validated(self) -> "OperatorConfig":
        """Reject nonsensical values instead of failing downstream."""
        if not self.github_user or "/" in self.github_user:
            raise ValueError(f"github_user must be a bare username, got {self.github_user!r}")
        if self.repos_dir.startswith("/"):
            raise ValueError("repos_dir must be relative to the project root")
        for name in ("clone_workers", "fetch_workers", "run_workers"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        if self.run_timeout_s < 1:
            raise ValueError("run_timeout_s must be >= 1")
        if self.stream_tail_bytes < 1:
            raise ValueError("stream_tail_bytes must be >= 1")
        return self


def load_config(project_root: Path | None = None) -> OperatorConfig:
    """Load ``data/operator_config.yaml`` with typed defaults.

    Unknown keys raise ``ValueError`` — a typo in the config must not be
    silently ignored (generator-failure masking rule).
    """
    root = project_root if project_root is not None else Path(__file__).resolve().parent.parent
    config_path = root / "data" / CONFIG_FILENAME
    overrides: dict = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{config_path} must contain a YAML mapping")
        known = {f.name for f in dataclasses.fields(OperatorConfig)}
        unknown = sorted(set(raw) - known)
        if unknown:
            raise ValueError(f"Unknown config keys in {config_path}: {unknown}")
        overrides = raw
    return OperatorConfig(**overrides).validated()
