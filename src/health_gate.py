"""Binary go/no-go health gate over the meta-operator output tree.

Nine stable checks (see ``CHECK_IDS``) verify the artifact chain end to end:
registry, clones, upstream verification, inventory, dashboard, catalog,
figures, manuscript variables, and runs (advisory). ``run_gate`` emits a
``GateReport`` that can be persisted and reloaded via ``save_gate``/``load_gate``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src import jsonio, project_paths

from src.models import GateCheck, GateReport, UPSTREAM_OK_STATES, from_dict, to_dict
from src.figures import FIGURE_FILENAMES

logger = logging.getLogger(__name__)

CHECK_IDS: tuple[str, ...] = (
    "registry_present",
    "clones_complete",
    "upstream_all_ok",
    "inventory_complete",
    "dashboard_present",
    "catalog_present",
    "figures_present",
    "manuscript_tokens_present",
    "runs_present",
)

_MIN_DASHBOARD_BYTES = 10_000
_MIN_FIGURE_BYTES = 10_000
_MIN_MANUSCRIPT_KEYS = 10
_MANUSCRIPT_VARIABLES = "manuscript_variables.json"

_REGISTRY_FIX = "fix: run scripts/10_build_registry.py"
_CLONE_FIX = "fix: run scripts/20_clone_corpus.py"
_FIGURES_FIX = "fix: run scripts/65_generate_figures.py"
_MANUSCRIPT_FIX = "fix: run scripts/z_generate_manuscript_variables.py --allow-draft"


def _iso_now() -> str:
    """Current UTC time as an ISO-8601 Z timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_registry(ddir: Path) -> dict[str, Any] | None:
    """Load the registry dict, or None when absent/corrupt."""
    try:
        raw = jsonio.read_json(ddir / project_paths.REPO_REGISTRY, required=True)
    except (KeyError, FileNotFoundError, RuntimeError, OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def _registry_names(ddir: Path) -> list[str] | None:
    """Sorted registry repo names, or None when the registry is unreadable."""
    raw = _read_registry(ddir)
    if raw is None:
        return None
    return sorted(str(r.get("name") or "") for r in raw.get("repos", []) or [])


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_registry(ddir: Path, expected_count: int | None) -> GateCheck:
    """registry_present: registry readable, nonempty, and count matches expected."""
    cid = "registry_present"
    raw = _read_registry(ddir)
    if raw is None:
        return GateCheck(cid, False, f"registry missing or unreadable — {_REGISTRY_FIX}")
    repos = raw.get("repos", []) or []
    count = len(repos)
    detail = f"registry present with {count} repos"
    if not repos:
        return GateCheck(cid, False, f"{detail} (empty) — {_REGISTRY_FIX}")
    if expected_count is not None and count != expected_count:
        return GateCheck(cid, False, f"{detail} — expected {expected_count}, got {count}")
    return GateCheck(cid, True, detail)


def _check_clones(project_root: Path, ddir: Path) -> GateCheck:
    """clones_complete: every registry name has a repos/<name>/.git directory."""
    cid = "clones_complete"
    names = _registry_names(ddir)
    if names is None:
        return GateCheck(cid, False, f"registry unreadable — {_REGISTRY_FIX}")
    rdir = project_paths.repos_dir(project_root)
    missing = sorted(n for n in names if not (rdir / n / ".git").is_dir())
    if missing:
        shown = ", ".join(missing[:10])
        extra = f" (+{len(missing) - 10} more)" if len(missing) > 10 else ""
        return GateCheck(cid, False, f"missing clones: {shown}{extra} — {_CLONE_FIX}")
    return GateCheck(cid, True, f"all {len(names)} clones present under repos/")


def _check_upstream(ddir: Path) -> GateCheck:
    """upstream_all_ok: upstream_status.json exists and every state is OK."""
    cid = "upstream_all_ok"
    try:
        raw = jsonio.read_json(ddir / project_paths.UPSTREAM_STATUS, required=True)
    except (KeyError, FileNotFoundError, RuntimeError, OSError, ValueError):
        return GateCheck(
            cid,
            False,
            "upstream_status.json missing — run the upstream verification step",
        )
    if not isinstance(raw, dict):
        return GateCheck(cid, False, "upstream_status.json is not a JSON object")
    entries = raw.get("repos", [])
    if not isinstance(entries, list) or not entries:
        return GateCheck(
            cid,
            False,
            "upstream_status.json has no repos entries — run the upstream verification step",
        )
    malformed = sum(1 for entry in entries if not isinstance(entry, dict))
    if malformed:
        return GateCheck(
            cid,
            False,
            f"upstream_status.json has {malformed} malformed (non-object) entries "
            "— re-run the upstream verification step",
        )
    offenders = sorted(
        (str(u.get("name") or "?"), str(u.get("state") or "?"))
        for u in entries
        if u.get("state") not in UPSTREAM_OK_STATES
    )
    if offenders:
        parts = [f"{name}: {state}" for name, state in offenders[:10]]
        extra = f" (+{len(offenders) - 10} more)" if len(offenders) > 10 else ""
        return GateCheck(
            cid,
            False,
            "offenders: " + ", ".join(parts) + extra
            + " — run the upstream verification step",
        )
    fresh = sum(1 for u in entries if u.get("fetched") is True)
    return GateCheck(
        cid,
        True,
        f"all {len(entries)} repos in {sorted(UPSTREAM_OK_STATES)} ({fresh} freshly fetched)",
    )


def _check_inventory(ddir: Path) -> GateCheck:
    """inventory_complete: names ∪ missing == registry names AND missing is empty."""
    cid = "inventory_complete"
    names = _registry_names(ddir)
    if names is None:
        return GateCheck(cid, False, f"registry unreadable — {_REGISTRY_FIX}")
    try:
        raw = jsonio.read_json(ddir / project_paths.INVENTORY, required=True)
    except (KeyError, FileNotFoundError, RuntimeError, OSError, ValueError):
        return GateCheck(cid, False, "inventory.json missing — run the inventory step")
    if not isinstance(raw, dict):
        return GateCheck(cid, False, "inventory.json is not a JSON object")
    got = {str(r.get("name") or "") for r in raw.get("repos", []) or [] if isinstance(r, dict)}
    missing_list = [str(m) for m in raw.get("missing", []) or []]
    covered = got | set(missing_list)
    expected = set(names)
    if missing_list:
        return GateCheck(
            cid,
            False,
            f"inventory reports {len(missing_list)} missing: "
            + ", ".join(sorted(missing_list)[:10])
            + " — run the inventory step",
        )
    if covered != expected:
        uncovered = sorted(expected - covered)
        unknown = sorted(covered - expected)
        detail = "inventory does not cover registry"
        if uncovered:
            detail += f"; uncovered: {', '.join(uncovered[:10])}"
        if unknown:
            detail += f"; not in registry: {', '.join(unknown[:10])}"
        return GateCheck(cid, False, detail + " — run the inventory step")
    return GateCheck(cid, True, f"inventory covers all {len(names)} repos, none missing")


def _check_dashboard(project_root: Path) -> GateCheck:
    """dashboard_present: web/dashboard.html exists and exceeds 10,000 bytes."""
    cid = "dashboard_present"
    path = project_paths.web_dir(project_root) / project_paths.DASHBOARD
    if not path.is_file():
        return GateCheck(cid, False, "dashboard.html missing — run the dashboard renderer")
    size = path.stat().st_size
    if size <= _MIN_DASHBOARD_BYTES:
        return GateCheck(
            cid,
            False,
            f"dashboard.html too small ({size} bytes, need > {_MIN_DASHBOARD_BYTES})"
            " — run the dashboard renderer",
        )
    return GateCheck(cid, True, f"dashboard.html present ({size} bytes)")


def _check_catalog(ddir: Path) -> GateCheck:
    """catalog_present: data/corpus_catalog.md exists and is non-empty."""
    cid = "catalog_present"
    path = ddir / project_paths.CORPUS_CATALOG
    if not path.is_file():
        return GateCheck(cid, False, "corpus_catalog.md missing — run the catalog renderer")
    if path.stat().st_size == 0:
        return GateCheck(cid, False, "corpus_catalog.md is empty — run the catalog renderer")
    return GateCheck(cid, True, f"corpus_catalog.md present ({path.stat().st_size} bytes)")


def _check_figures(project_root: Path) -> GateCheck:
    """figures_present: every figure PNG exists under output/figures and is >10 KB."""
    cid = "figures_present"
    fdir = project_paths.figures_dir(project_root)
    missing = [name for name in sorted(FIGURE_FILENAMES) if not (fdir / name).is_file()]
    if missing:
        return GateCheck(
            cid,
            False,
            f"missing {len(missing)}/{len(FIGURE_FILENAMES)} figures "
            f"({', '.join(missing)}) — {_FIGURES_FIX}",
        )
    small = [
        (name, (fdir / name).stat().st_size)
        for name in sorted(FIGURE_FILENAMES)
        if (fdir / name).stat().st_size <= _MIN_FIGURE_BYTES
    ]
    if small:
        detail = ", ".join(f"{name} ({size} bytes)" for name, size in small)
        return GateCheck(
            cid,
            False,
            f"figure(s) too small: {detail}, need > {_MIN_FIGURE_BYTES} bytes — {_FIGURES_FIX}",
        )
    return GateCheck(
        cid,
        True,
        f"all {len(FIGURE_FILENAMES)} figures present under output/{project_paths.FIGURES_DIRNAME}/",
    )


def _check_manuscript_variables(ddir: Path) -> GateCheck:
    """manuscript_tokens_present: manuscript_variables.json is an object with >= 10 keys."""
    cid = "manuscript_tokens_present"
    path = ddir / _MANUSCRIPT_VARIABLES
    if not path.is_file():
        return GateCheck(cid, False, f"{_MANUSCRIPT_VARIABLES} missing — {_MANUSCRIPT_FIX}")
    try:
        raw = jsonio.read_json(path, required=False)
    except ValueError:  # json.JSONDecodeError: corruption, not absence
        return GateCheck(cid, False, f"{_MANUSCRIPT_VARIABLES} is not valid JSON — {_MANUSCRIPT_FIX}")
    if not isinstance(raw, dict):
        return GateCheck(cid, False, f"{_MANUSCRIPT_VARIABLES} is not a JSON object — {_MANUSCRIPT_FIX}")
    if len(raw) < _MIN_MANUSCRIPT_KEYS:
        return GateCheck(
            cid,
            False,
            f"{_MANUSCRIPT_VARIABLES} has {len(raw)} keys, need >= {_MIN_MANUSCRIPT_KEYS} — {_MANUSCRIPT_FIX}",
        )
    return GateCheck(cid, True, f"{_MANUSCRIPT_VARIABLES} present ({len(raw)} variables)")


def _check_runs(ddir: Path) -> GateCheck:
    """runs_present (advisory): always passes; reports the latest run if any."""
    cid = "runs_present"
    rdir = ddir / project_paths.RUNS_DIRNAME
    if rdir.is_dir():
        run_dirs = sorted(
            (x for x in rdir.iterdir() if x.is_dir()), key=lambda p: p.name, reverse=True
        )
        for d in run_dirs:
            if (d / "results.json").is_file():
                return GateCheck(cid, True, f"last run {d.name}")
    return GateCheck(cid, True, "no runs yet (advisory)")


# ---------------------------------------------------------------------------
# Gate entry points
# ---------------------------------------------------------------------------


def run_gate(project_root: Path, *, expected_count: int | None = None) -> GateReport:
    """Run all nine checks against ``project_root`` and return the report."""
    root = Path(project_root)
    ddir = project_paths.data_dir(root)
    checks = [
        _check_registry(ddir, expected_count),
        _check_clones(root, ddir),
        _check_upstream(ddir),
        _check_inventory(ddir),
        _check_dashboard(root),
        _check_figures(root),
        _check_catalog(ddir),
        _check_manuscript_variables(ddir),
        _check_runs(ddir),
    ]
    report = GateReport(checks=checks, generated_at=_iso_now())
    return report


def save_gate(report: GateReport, project_root: Path) -> Path:
    """Persist a GateReport to ``output/data/health_gate.json`` (atomic)."""
    path = project_paths.data_dir(project_root) / project_paths.HEALTH_GATE
    payload = {
        "generated_at": report.generated_at,
        "passed": report.passed,
        "checks": [to_dict(c) for c in report.checks],
    }
    jsonio.write_json(path, payload)
    return path


def load_gate(project_root: Path) -> GateReport:
    """Reload a persisted GateReport, reconstructing GateCheck objects explicitly."""
    path = project_paths.data_dir(project_root) / project_paths.HEALTH_GATE
    raw = jsonio.read_json(path, required=True)
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object")
    checks = [from_dict(GateCheck, c) for c in raw.get("checks", [])]
    return GateReport(checks=checks, generated_at=str(raw.get("generated_at", "")))