# AI Agent Instructions — Dicklesworthstone Meta-Operator

Read this file before touching any other file in this project.

## Rule 1: Reading order is mandatory

| Document | Governs | Skip consequence |
| --- | --- | --- |
| This file | All modifications | Risk all violations below |
| `architecture.md` | Module boundaries, artifact shapes | Broken cross-module contracts |
| `testing_philosophy.md` | Any test modification | Mocks, offline violations |
| `../AGENTS.md` | Layer contract, vocabulary | Scripts growing business logic |

## Rule 2: Coverage gate — ≥90 % on `src/`, zero mocks

```bash
cd projects/ongoing/Code_Tools/dicklesworthstone_meta_operator
uv run pytest tests/ --cov=src --cov-fail-under=90 -q
```

- No `unittest.mock`, `MagicMock`, `@patch`, `create_autospec` anywhere in `tests/`.
- Git behavior is tested against REAL fixture repos built with `git init`/`commit`
  in `tmp_path` — never simulated.
- `pytest.MonkeyPatch` on module attributes is allowed only for error-path
  injection (documented template pattern), never to fake function returns.
- Tests are OFFLINE. No github.com access. The `gh` boundary is tested via a
  PATH-stubbed fixture script (a real executable), not a mock object.
- If coverage drops: add behavioral tests, do not delete tests or add
  `# pragma: no cover` without a written reason.

## Rule 3: Thin orchestrator boundary

`scripts/` = argv parsing + delegation + artifact writes. Any classification
logic (which state, which command, which repos) lives in `src/` behind tests.

## Rule 4: `output/` is disposable — never edit generated files

Change the generator (`src/` + scripts), then re-run the stage. The stage
numbering (`10_` → `70_`) is the pipeline order; a re-run of any stage must be
safe given its predecessors' artifacts.

## Rule 5: Determinism

All artifacts sort entities by name before serialization. HTML/markdown
renderers must be pure functions of their payload (two calls, identical
output, no wall-clock beyond the single `generated_at` field).

## Rule 6: Failure discipline

Subprocess failures become typed outcomes (`CloneOutcome.status=failed`,
`RunResult.timed_out`, `GateCheck.passed=False`) — never swallowed, never
`2>/dev/null || true`. A stage that cannot verify prints a fix hint and exits
nonzero.

## Verification checklist (run before submitting changes)

```bash
# 1. Tests + coverage gate
cd projects/ongoing/Code_Tools/dicklesworthstone_meta_operator && uv run pytest tests/ --cov=src --cov-fail-under=90 -q

# 2. No mocks anywhere in tests/
grep -r "unittest.mock\|MagicMock\|@patch\|create_autospec" tests/ || echo "Clean — no mocks found"

# 3. Pipeline still consistent after touching any producer/consumer
uv run python scripts/60_dashboard.py && uv run python scripts/70_health_gate.py
```
