"""Deterministic PNG figure builders for the meta-operator manuscript.

Every builder takes plain artifact dicts (the ``to_dict`` shapes persisted
under ``output/data/``) plus an output path and renders one static matplotlib
figure: sorted inputs, a fixed colorblind-safe palette, and no timestamps in
either content or PNG metadata — so identical inputs yield byte-identical
files. Figures are written at 300 DPI with a tight bounding box.
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # must run before pyplot is imported anywhere

import matplotlib.pyplot as plt  # noqa: E402

from src.models import UPSTREAM_OK_STATES  # noqa: E402

logger = logging.getLogger(__name__)

FIGURE_FILENAMES: frozenset[str] = frozenset(
    {
        "fig_state_distribution.png",
        "fig_language_distribution.png",
        "fig_loc_size.png",
        "fig_staleness.png",
    }
)

PNG_DPI = 300
PNG_METADATA: dict[str, str] = {"Software": "dicklesworthstone_meta_operator"}

# Fixed Okabe-Ito colorblind-safe palette (constant hex, never computed).
_OK_GREEN = "#009E73"
_ATTENTION_AMBER = "#E69F00"
_BLUE = "#0072B2"
_SKY = "#56B4E9"
_VERMILLION = "#D55E00"
_PINK = "#CC79A7"
_GREY = "#999999"

# Colors assigned to the top-6 primary languages in frequency order.
_LANGUAGE_PALETTE: tuple[str, ...] = (_BLUE, _VERMILLION, _OK_GREEN, _SKY, _PINK, _ATTENTION_AMBER)


def _save(fig: plt.Figure, out_path: Path) -> Path:
    """Save ``fig`` at fixed DPI/tight bbox/metadata, close it, return the path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=PNG_DPI, bbox_inches="tight", metadata=PNG_METADATA)
    plt.close(fig)
    logger.info("figure written: %s", out_path)
    return out_path


def _horizontal_bar(
    counts: Counter[str],
    color_for: Any,
    title: str,
    xlabel: str,
    out_path: Path,
) -> Path:
    """Render a labeled horizontal bar chart of ``counts``, sorted descending."""
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    labels = [key for key, _ in items]
    values = [value for _, value in items]
    fig, ax = plt.subplots(figsize=(8.0, max(2.0, 0.6 * len(labels) + 1.2)))
    bars = ax.barh(labels, values, color=[color_for(label) for label in labels])
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2.0,
            f" {value}",
            va="center",
        )
    ax.set_xlim(0, max(values) * 1.15)  # headroom for the count labels
    return _save(fig, out_path)


def build_state_distribution_figure(
    statuses: list[dict[str, Any]], out_path: Path
) -> Path:
    """Horizontal bar of ``UpstreamStatus.state`` counts.

    OK states (``on_upstream``, ``unborn``) render in the green family, every
    other state in the amber family; bars are sorted by count descending and
    carry explicit count labels.

    Raises:
        ValueError: If ``statuses`` is empty.
    """
    if not statuses:
        raise ValueError("no upstream statuses provided")
    counts = Counter(str(status.get("state") or "unknown") for status in statuses)
    return _horizontal_bar(
        counts,
        color_for=lambda state: _OK_GREEN if state in UPSTREAM_OK_STATES else _ATTENTION_AMBER,
        title="Upstream state distribution",
        xlabel="repos",
        out_path=Path(out_path),
    )


def build_language_distribution_figure(
    repos: list[dict[str, Any]], out_path: Path
) -> Path:
    """Horizontal bar of repos per GitHub ``language`` (missing/empty -> "Other").

    Raises:
        ValueError: If ``repos`` is empty.
    """
    if not repos:
        raise ValueError("no registry repos provided")
    counts: Counter[str] = Counter()
    for repo in repos:
        language = str(repo.get("language") or "").strip()
        counts[language or "Other"] += 1
    return _horizontal_bar(
        counts,
        color_for=lambda language: _GREY if language == "Other" else _BLUE,
        title="Language distribution",
        xlabel="repos",
        out_path=Path(out_path),
    )


def build_loc_size_figure(
    inventory_repos: list[dict[str, Any]], out_path: Path
) -> Path:
    """Log-log scatter of ``total_loc`` (x) vs ``size_kb`` (y), colored by language.

    The six most frequent primary languages get fixed palette colors; every
    other language collapses into a grey "Other" bucket. Entries lacking a
    positive ``total_loc``/``size_kb`` (e.g. inventory rows with no registry
    twin to join against) are skipped rather than force-plotted.

    Raises:
        ValueError: If no entry has both a positive ``total_loc`` and ``size_kb``.
    """
    usable = [
        entry
        for entry in inventory_repos
        if isinstance(entry.get("total_loc"), (int, float))
        and entry["total_loc"] > 0
        and isinstance(entry.get("size_kb"), (int, float))
        and entry["size_kb"] > 0
    ]
    if not usable:
        raise ValueError("no inventory entries with positive total_loc and size_kb")

    lang_counts: Counter[str] = Counter(
        str(entry.get("primary_language") or "").strip() or "Other" for entry in usable
    )
    top_languages = [
        name
        for name, _ in sorted(lang_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
    ]

    def _bucket(language: str) -> str:
        return language if language in top_languages else "Other"

    points_by_bucket: dict[str, list[tuple[float, float]]] = {}
    for entry in usable:
        language = str(entry.get("primary_language") or "").strip() or "Other"
        points_by_bucket.setdefault(_bucket(language), []).append(
            (float(entry["total_loc"]), float(entry["size_kb"]))
        )

    fig, ax = plt.subplots(figsize=(7.0, 5.5))
    ax.set_xscale("log")
    ax.set_yscale("log")
    for bucket, points in sorted(points_by_bucket.items()):
        color = (
            _LANGUAGE_PALETTE[top_languages.index(bucket)]
            if bucket in top_languages
            else _GREY
        )
        ax.scatter(
            [x for x, _ in points],
            [y for _, y in points],
            s=28,
            color=color,
            label=bucket,
        )
    ax.set_xlabel("total LOC")
    ax.set_ylabel("repo size (KB)")
    ax.set_title("Repository size vs LOC")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(title="primary language")
    return _save(fig, Path(out_path))


def build_staleness_figure(
    inventory_repos: list[dict[str, Any]],
    out_path: Path,
    now: datetime | None = None,
) -> Path:
    """Histogram of whole-day repo ages from ``last_commit_date``.

    Entries with an empty/unparseable ``last_commit_date`` are skipped, as are
    future-dated commits (negative ages). Vertical lines mark the median and
    maximum age.

    Raises:
        ValueError: If no entry yields a usable non-negative age.
    """
    now = now if now is not None else datetime.now(timezone.utc)
    ages: list[int] = []
    for entry in inventory_repos:
        raw = str(entry.get("last_commit_date") or "").strip()
        if not raw:
            continue
        try:
            committed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("skipping unparseable last_commit_date: %r", raw)
            continue
        if committed.tzinfo is None:
            committed = committed.replace(tzinfo=timezone.utc)
        age_days = (now - committed).days
        if age_days >= 0:
            ages.append(age_days)
    if not ages:
        raise ValueError("no inventory entries with a usable last_commit_date")

    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    bins = max(1, min(20, len(set(ages))))
    ax.hist(ages, bins=bins, color=_BLUE, edgecolor="white")
    ax.set_xlabel("days since last commit")
    ax.set_ylabel("repos")
    ax.set_title("Repository staleness")
    median_days = statistics.median(ages)
    oldest = max(ages)
    ax.axvline(
        median_days,
        color=_VERMILLION,
        linestyle="--",
        linewidth=1.5,
        label=f"median {median_days:g}d",
    )
    ax.axvline(
        oldest,
        color=_ATTENTION_AMBER,
        linestyle="--",
        linewidth=1.5,
        label=f"max {oldest}d",
    )
    ax.legend()
    return _save(fig, Path(out_path))


def build_all_figures(
    registry: dict[str, Any],
    upstream: dict[str, Any],
    inventory: dict[str, Any],
    out_dir: Path,
) -> list[Path]:
    """Render all four manuscript figures into ``out_dir`` (mkdir'd); return paths.

    ``size_kb`` lives on registry entries, so each inventory row is enriched
    with its registry twin's value before the LOC/size scatter; inventory rows
    missing from the registry simply carry no size and are skipped there.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    registry_repos = list(registry.get("repos") or [])
    upstream_repos = list(upstream.get("repos") or [])
    inventory_repos = list(inventory.get("repos") or [])
    size_by_name = {
        str(repo.get("name") or ""): repo.get("size_kb") for repo in registry_repos
    }
    merged_inventory: list[dict[str, Any]] = []
    for entry in inventory_repos:
        merged = dict(entry)
        merged.setdefault("size_kb", size_by_name.get(str(entry.get("name") or "")))
        merged_inventory.append(merged)
    written = [
        build_state_distribution_figure(
            upstream_repos, out_dir / "fig_state_distribution.png"
        ),
        build_language_distribution_figure(
            registry_repos, out_dir / "fig_language_distribution.png"
        ),
        build_loc_size_figure(merged_inventory, out_dir / "fig_loc_size.png"),
        build_staleness_figure(inventory_repos, out_dir / "fig_staleness.png"),
    ]
    logger.info("wrote %d figures to %s", len(written), out_dir)
    return written
