"""Manuscript variable generation for the meta-operator.

The accuracy contract (template discipline): every numeric claim in the
manuscript prose is a ``{{TOKEN}}`` and every token is emitted by
:func:`generate_variables` — one function, one test
(``tests/test_manuscript_variables.py``), zero hand-maintained numbers.

Reads (all generated, tracked artifacts — never hand-edited):
- ``output/data/repo_registry.json``    — corpus enumeration
- ``output/data/upstream_status.json``  — verification snapshot
- ``output/data/inventory.json``        — interpretability profiles
- ``output/data/health_gate.json``      — binary gate report
- ``docs/manuscript/config.yaml``       — paper metadata (title/version/keywords)

Called exclusively by ``scripts/z_generate_manuscript_variables.py``
(thin orchestrator). Strict mode (default) fails when a required artifact is
missing; ``require_analysis_outputs=False`` (script ``--allow-draft``) emits
``"N/A"`` placeholders for early drafts that may render without evidence.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.jsonio import write_json
from src.project_paths import data_dir

REQUIRED_ARTIFACTS = (
    "repo_registry.json",
    "upstream_status.json",
    "inventory.json",
    "health_gate.json",
)

# Figure filenames the manuscript references; must stay aligned with
# src/figures.FIGURE_FILENAMES (asserted by tests/test_manuscript_variables.py).
EXPECTED_FIGURES: tuple[str, ...] = (
    "fig_state_distribution.png",
    "fig_language_distribution.png",
    "fig_loc_size.png",
    "fig_staleness.png",
)

_NA = "N/A"
_TOP_LANGUAGES = 5


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON artifact; missing files raise with a fix hint."""
    if not path.exists():
        raise FileNotFoundError(
            f"required manuscript input missing: {path} — run the pipeline "
            "stages (scripts/10..70) first"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _sha8_file(path: Path) -> str:
    """First 8 hex chars of SHA-256 over the file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def _thousands(n: int) -> str:
    return f"{n:,}"


def _days_since(iso: str, now: datetime) -> int | None:
    """Whole-day age of an ISO-8601 timestamp; None when absent/unparseable."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, (now - dt).days)


def generate_variables(
    project_root: Path, *, require_analysis_outputs: bool = True
) -> dict[str, str]:
    """Build the flat ``UPPERCASE_KEY -> value`` token map.

    When ``require_analysis_outputs`` is True (the pipeline path), a missing
    required artifact raises ``FileNotFoundError``; with False (draft mode),
    result-derived tokens fall back to ``"N/A"`` so early drafts render.
    """
    root = Path(project_root)
    ddir = data_dir(root)

    tokens: dict[str, str] = {}

    def put(key: str, value: Any) -> None:
        # Placeholder semantics: a *missing value* (None, empty) becomes N/A in
        # draft mode; a legitimate zero (e.g. 0 forks) is a real value.
        tokens[key] = _NA if value is None or value == "" else str(value)
    figures_dir = root / "output" / "figures"

    def need(path: Path) -> Path:
        if require_analysis_outputs and not path.exists():
            raise FileNotFoundError(
                f"required manuscript input missing: {path} — run the pipeline "
                "stages (scripts/10..70) first"
            )
        return path

    def opt(path: Path) -> dict[str, Any] | None:
        return _load_json(path) if path.exists() else None

    registry = opt(need(ddir / "repo_registry.json"))
    upstream = opt(need(ddir / "upstream_status.json"))
    inventory = opt(need(ddir / "inventory.json"))
    gate = opt(need(ddir / "health_gate.json"))


    # -- paper metadata -----------------------------------------------------
    config_path = root / "docs" / "manuscript" / "config.yaml"
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    elif require_analysis_outputs:
        raise FileNotFoundError(
            f"manuscript config missing: {config_path}"
        )
    else:
        config = {}
    paper = config.get("paper") or {}
    put("CONFIG_TITLE", paper.get("title"))
    put("CONFIG_VERSION", paper.get("version"))
    keywords = config.get("keywords") or []
    put("CONFIG_KEYWORDS", ", ".join(keywords) if keywords else None)

    # -- registry-derived corpus tokens -------------------------------------
    if registry is not None:
        repos = registry.get("repos") or []
        put("CONFIG_GITHUB_USER", registry.get("github_user"))
        put("CORPUS_REPO_TOTAL", len(repos))
        put("CORPUS_FORK_TOTAL", sum(1 for r in repos if r.get("fork")))
        put("CORPUS_ARCHIVED_TOTAL", sum(1 for r in repos if r.get("archived")))
        lang_counts: dict[str, int] = {}
        total_size_kb = 0
        for r in repos:
            lang = str(r.get("language") or "").strip() or "Other"
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
            total_size_kb += int(r.get("size_kb") or 0)
        ranked = sorted(lang_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        put("CORPUS_LANG_COUNT", len(ranked))
        for i in range(_TOP_LANGUAGES):
            if i < len(ranked):
                put(f"CORPUS_LANG{i + 1}_NAME", ranked[i][0])
                put(f"CORPUS_LANG{i + 1}_COUNT", ranked[i][1])
            else:
                put(f"CORPUS_LANG{i + 1}_NAME", _NA)
                put(f"CORPUS_LANG{i + 1}_COUNT", _NA)
        top5 = {name for name, _ in ranked[:_TOP_LANGUAGES]}
        put(
            "CORPUS_LANG_OTHER_REPOS",
            sum(c for name, c in lang_counts.items() if name not in top5),
        )
        put("CORPUS_TOTAL_SIZE_GB", f"{total_size_kb / 1e6:.2f}" if repos else None)
    else:
        put("CONFIG_GITHUB_USER", None)
        put("CORPUS_REPO_TOTAL", None)
        put("CORPUS_FORK_TOTAL", None)
        put("CORPUS_ARCHIVED_TOTAL", None)
        put("CORPUS_LANG_COUNT", None)
        for i in range(_TOP_LANGUAGES):
            put(f"CORPUS_LANG{i + 1}_NAME", None)
            put(f"CORPUS_LANG{i + 1}_COUNT", None)
        put("CORPUS_LANG_OTHER_REPOS", None)
        put("CORPUS_TOTAL_SIZE_GB", None)

    # -- inventory-derived interpretability tokens ---------------------------
    inv_repos = (inventory or {}).get("repos") or []
    if inventory is not None and inv_repos:
        total_loc = sum(int(r.get("total_loc") or 0) for r in inv_repos)
        with_tests = sum(1 for r in inv_repos if r.get("has_tests"))
        put("CORPUS_TOTAL_LOC", _thousands(total_loc))
        put("CORPUS_WITH_TESTS", with_tests)
        put("CORPUS_WITH_TESTS_PCT", f"{100 * with_tests / len(inv_repos):.0f}")
        manifests: dict[str, int] = {}
        ages: list[int] = []
        now = datetime.now(timezone.utc)
        for r in inv_repos:
            for key in (r.get("manifests") or {}):
                manifests[key] = manifests.get(key, 0) + 1
            age = _days_since(str(r.get("last_commit_date") or ""), now)
            if age is not None:
                ages.append(age)
        put("CORPUS_CI_WORKFLOWS", manifests.get(".github/workflows"))
        put("CORPUS_CARGO_MANIFESTS", manifests.get("Cargo.toml"))
        put("CORPUS_PYPROJECT_MANIFESTS", manifests.get("pyproject.toml"))
        put("CORPUS_STALE_MAX_DAYS", max(ages) if ages else None)
        put(
            "CORPUS_STALE_MEDIAN_DAYS",
            sorted(ages)[len(ages) // 2] if ages else None,
        )
    else:
        for key in (
            "CORPUS_TOTAL_LOC", "CORPUS_WITH_TESTS", "CORPUS_WITH_TESTS_PCT",
            "CORPUS_CI_WORKFLOWS", "CORPUS_CARGO_MANIFESTS",
            "CORPUS_PYPROJECT_MANIFESTS", "CORPUS_STALE_MAX_DAYS",
            "CORPUS_STALE_MEDIAN_DAYS",
        ):
            put(key, None)

    # -- upstream verification tokens ----------------------------------------
    statuses = (upstream or {}).get("repos") or []
    states: dict[str, int] = {}
    for s in statuses:
        states[str(s.get("state") or "?")] = states.get(str(s.get("state") or "?"), 0) + 1
    if upstream is not None:
        on, behind, unborn = states.get("on_upstream", 0), states.get("behind", 0), states.get("unborn", 0)
        ok = on + unborn
        total = len(statuses)
        put("VERIFY_TOTAL", total)
        put("VERIFY_ON_UPSTREAM", on)
        put("VERIFY_BEHIND", behind)
        put("VERIFY_UNBORN", unborn)
        put("VERIFY_OTHER_NOT_OK", total - ok - behind)
        put("VERIFY_OK", ok)
        put("VERIFY_OK_PCT", f"{100 * ok / total:.1f}" if total else None)
        put("VERIFY_GENERATED_AT", upstream.get("generated_at"))
    else:
        for key in (
            "VERIFY_TOTAL", "VERIFY_ON_UPSTREAM", "VERIFY_BEHIND", "VERIFY_UNBORN",
            "VERIFY_OTHER_NOT_OK", "VERIFY_OK", "VERIFY_OK_PCT", "VERIFY_GENERATED_AT",
        ):
            put(key, None)

    # -- gate tokens ----------------------------------------------------------
    checks = (gate or {}).get("checks") or []
    if gate is not None:
        put("GATE_VERDICT", "GO" if gate.get("passed") else "NO-GO")
        put("GATE_CHECKS_TOTAL", len(checks))
        put("GATE_CHECKS_PASSED", sum(1 for c in checks if c.get("passed")))
    else:
        put("GATE_VERDICT", None)
        put("GATE_CHECKS_TOTAL", None)
        put("GATE_CHECKS_PASSED", None)

    # -- figure inventory ------------------------------------------------------
    figure_count = sum(1 for f in EXPECTED_FIGURES if (figures_dir / f).exists())
    put("FIGURE_COUNT", figure_count)

    # -- artifact integrity hashes --------------------------------------------
    artifact_keys = {
        "repo_registry.json": "ARTIFACT_SHA8_REGISTRY",
        "upstream_status.json": "ARTIFACT_SHA8_UPSTREAM",
        "inventory.json": "ARTIFACT_SHA8_INVENTORY",
        "health_gate.json": "ARTIFACT_SHA8_GATE",
    }
    for filename, key in artifact_keys.items():
        path = ddir / filename
        if path.exists():
            put(key, _sha8_file(path))
        else:
            put(key, None)

    return tokens


def save_variables(variables: dict[str, str], output_path: Path) -> Path:
    """Write the token map for rendering and debugging (tracked artifact)."""
    return write_json(output_path, variables)
