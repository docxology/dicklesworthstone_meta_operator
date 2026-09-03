"""Meta-operator over the Dicklesworthstone GitHub corpus.

Modules:
    models          — typed dataclasses for every cross-module contract (pure)
    config          — typed loader for data/operator_config.yaml
    project_paths   — project root + standard directory resolution
    github_client   — `gh api` wrapper: enumerate repos (subprocess boundary)
    registry        — build/save/load the repo registry (output/data)
    cloner          — parallel, idempotent corpus cloning into repos/
    upstream_check  — per-clone upstream-default-branch verification
    inventory       — per-repo interpretability profiles (languages, manifests,
                      entry points, tests, README digests, activity)
    orchestrator    — selector-filtered command execution across the corpus
    dashboard       — static self-contained HTML dashboard (output/web)
    health_gate     — binary go/no-go gate over the full artifact set

Import convention: `from src.models import RepoMeta` (pythonpath includes
project root). `src/` must not import template `infrastructure.*`.
"""

__all__ = [
    "models",
    "config",
    "project_paths",
    "github_client",
    "registry",
    "cloner",
    "upstream_check",
    "inventory",
    "orchestrator",
    "dashboard",
    "health_gate",
]
