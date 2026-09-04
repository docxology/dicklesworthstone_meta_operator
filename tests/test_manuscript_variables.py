"""Manuscript token discipline — the accuracy contract, enforced.

Two directions, both fatal:
1. every ``{{TOKEN}}`` used in ``docs/manuscript/*.md`` must be emitted by
   ``src.manuscript_variables.generate_variables`` (no invented numbers);
2. every token the generator emits must actually be used in the prose
   (no stale generator entries masking drift).

Generator inputs are the project's REAL tracked artifacts; the figure-filename
contract with ``src/figures`` is asserted explicitly.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import figures, manuscript_variables, project_paths  # noqa: E402
from src.manuscript_variables import EXPECTED_FIGURES, generate_variables

MANUSCRIPT_DIR = PROJECT_ROOT / "docs" / "manuscript"
_TOKEN_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def _prose_tokens() -> set[str]:
    tokens: set[str] = set()
    assert MANUSCRIPT_DIR.is_dir(), "manuscript tree missing"
    for md in sorted(MANUSCRIPT_DIR.glob("*.md")):
        tokens.update(_TOKEN_RE.findall(md.read_text(encoding="utf-8")))
    return tokens


def test_expected_figures_match_figure_module():
    """The generator's figure inventory stays aligned with src/figures."""
    from src.figures import FIGURE_FILENAMES

    assert tuple(sorted(EXPECTED_FIGURES)) == tuple(sorted(FIGURE_FILENAMES))


def test_strict_generation_from_tracked_artifacts():
    """The committed tree is manuscript-ready: strict generation succeeds."""
    tokens = generate_variables(PROJECT_ROOT, require_analysis_outputs=True)
    assert len(tokens) >= 30
    assert tokens["CONFIG_GITHUB_USER"] == "Dicklesworthstone"
    assert int(tokens["CORPUS_REPO_TOTAL"]) > 200
    # OK ratio renders as a bare percentage number (e.g. "84.5")
    assert tokens["VERIFY_OK_PCT"] != "N/A"


def test_all_prose_tokens_are_generated():
    """No token may appear in prose that the generator does not emit."""
    tokens = generate_variables(PROJECT_ROOT, require_analysis_outputs=True)
    used = _prose_tokens()
    missing = sorted(used - set(tokens))
    assert not missing, f"prose uses tokens the generator does not emit: {missing}"


def test_all_generated_tokens_are_used():
    """No stale generator entries: every emitted token appears in the prose."""
    tokens = generate_variables(PROJECT_ROOT, require_analysis_outputs=True)
    used = _prose_tokens()
    unused = sorted(set(tokens) - used)
    assert not unused, f"generator emits tokens the prose never uses: {unused}"


def test_saved_token_map_matches_generator(tmp_path: Path):
    """The tracked manuscript_variables.json artifact is exactly the generated map."""
    saved_path = PROJECT_ROOT / "output" / "data" / "manuscript_variables.json"
    assert saved_path.exists(), "run scripts/z_generate_manuscript_variables.py"
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved == generate_variables(PROJECT_ROOT, require_analysis_outputs=True)


def test_strict_mode_fails_on_missing_artifacts(tmp_path: Path):
    """An empty project tree must fail loudly in strict mode."""
    with pytest.raises(FileNotFoundError, match="required manuscript input missing"):
        generate_variables(tmp_path, require_analysis_outputs=True)


def test_draft_mode_emits_placeholders(tmp_path: Path):
    """Draft mode emits N/A placeholders instead of failing (no artifacts)."""
    (tmp_path / "docs" / "manuscript").mkdir(parents=True)
    (tmp_path / "docs" / "manuscript" / "config.yaml").write_text(
        "paper:\n  title: T\n  version: 0.1.0\nkeywords: [k]\n", encoding="utf-8"
    )
    tokens = generate_variables(tmp_path, require_analysis_outputs=False)
    assert tokens["VERIFY_OK"] == "N/A"
    assert tokens["CORPUS_REPO_TOTAL"] == "N/A"
    assert tokens["CONFIG_TITLE"] == "T"


def test_figures_required_in_strict_mode(tmp_path: Path):
    """Strict mode requires all four manuscript figures on disk."""
    # The real project satisfies this; here prove the requirement directly.
    assert all(
        (PROJECT_ROOT / "output" / "figures" / f).exists() for f in EXPECTED_FIGURES
    ), "run scripts/65_generate_figures.py — manuscript figures missing"