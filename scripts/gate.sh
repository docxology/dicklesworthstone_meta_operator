#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 0 ] || [ -n "${PYTEST_ADDOPTS:-}" ]; then
  echo "gate: test-selection overrides are not allowed" >&2
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
GATE_DIR="$(mktemp -d "${TMPDIR:?}/dmo-gate.XXXXXXXX")"
export COVERAGE_FILE="$GATE_DIR/.coverage"
export MPLCONFIGDIR="$GATE_DIR/matplotlib"
export PYTHONDONTWRITEBYTECODE=1
export UV_OFFLINE=1
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$ROOT/.venv}"
uv lock --offline --check
uv run --offline --locked --no-sync python - "$ROOT" "$GATE_DIR/source" <<'PY'
from pathlib import Path
import shutil
import sys
root, target = map(Path, sys.argv[1:])
target.mkdir()
for relative in ("src", "scripts", "tests", "docs", "data", "output/data", "output/figures"):
    shutil.copytree(root / relative, target / relative, symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for relative in ("pyproject.toml", "uv.lock", "AGENTS.md", "README.md"):
    shutil.copy2(root / relative, target / relative)
print(f"source gate snapshot: {target}")
PY
cd "$GATE_DIR/source"
export PYTHONPATH="$PWD:$PWD/src"
uv run --offline --locked --no-sync python scripts/z_generate_manuscript_variables.py
uv run --offline --locked --no-sync python -m pytest tests/ --cov=src --cov-fail-under=90 \
  --cov-report=term-missing -p no:cacheprovider --basetemp="$GATE_DIR/pytest"
uv run --offline --locked --no-sync python scripts/65_generate_figures.py --out-dir "$GATE_DIR/figures"
test -s "$GATE_DIR/figures/fig_state_distribution.png"
uv run --offline --locked --no-sync python - <<'PY'
from pathlib import Path
import re
import sys
pattern = re.compile(r"unittest\.mock|MagicMock|@\s*patch\b|create_autospec")
hits = [str(path) for path in Path("tests").rglob("*.py") if pattern.search(path.read_text())]
if hits:
    print("zero-mock violations:", hits, file=sys.stderr)
    raise SystemExit(1)
print("zero-mock audit passed")
PY
echo "offline source gate passed; retained diagnostic snapshot and artifacts: $GATE_DIR"
