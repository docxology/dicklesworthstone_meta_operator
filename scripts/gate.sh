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
uv run --offline --locked --no-sync python - "$ROOT" "$GATE_DIR" <<'PY'
from pathlib import Path
import sys
from src.source_evidence import prepare_snapshot
root, evidence_dir = map(Path, sys.argv[1:])
print(f"source gate snapshot: {prepare_snapshot(root, evidence_dir)}")
PY
cd "$GATE_DIR/source"
export PYTHONPATH="$PWD:$PWD/src"
finish() {
  local gate_exit=$?
  trap - EXIT
  if ! uv run --offline --locked --no-sync python - "$ROOT" "$GATE_DIR" "$gate_exit" <<'PY'
from pathlib import Path
import sys
from src.source_evidence import finish_gate
report = finish_gate(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
print(f"source gate receipt: {sys.argv[2]}/source_gate.json")
print("offline source gate passed" if report.passed else "offline source gate failed; inspect receipt checks")
raise SystemExit(0 if report.passed else 1)
PY
  then
    if [ "$gate_exit" -eq 0 ]; then gate_exit=1; fi
  fi
  exit "$gate_exit"
}
trap finish EXIT
uv run --offline --locked --no-sync python scripts/z_generate_manuscript_variables.py
uv run --offline --locked --no-sync python -m pytest tests/ --cov=src --cov-fail-under=90 \
  --cov-report=term-missing --cov-report="json:$GATE_DIR/coverage.json" \
  --junitxml="$GATE_DIR/pytest.xml" -p no:cacheprovider --basetemp="$GATE_DIR/pytest"
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
echo "source test and figure steps completed; retained snapshot and artifacts: $GATE_DIR"
