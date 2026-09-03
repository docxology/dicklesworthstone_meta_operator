# scripts/ — Agent Guide

## Thin orchestrator pattern

A "thin orchestrator" strictly coordinates: parse argv → load config/artifacts
→ call `src/` → write artifact → print summary → return exit code. If you are
about to write an `if` that classifies repo state, picks a command, or filters
repos — that logic belongs in `src/` behind a test.

## Rules

- `REPO_ROOT = Path(__file__).resolve().parents[1]` + `sys.path.insert` header
  (keeps scripts runnable from any cwd).
- Exit codes are meaningful: 0 success, 1 = stage-level failure with printed
  diagnostics and a fix hint naming the script to run.
- Never mask failures (`|| true`, broad except-and-continue). Typed outcomes
  live in `src/`; scripts surface them.
- Numbered prefixes are pipeline order; a new stage between N and M renumbers
  or takes the next free number — never repurpose an existing number.
- `output/` writes go through `src/jsonio` (atomic) or the module that owns
  the artifact.

## Common issues

- `registry missing` → run `10_build_registry.py` first (or the fix hint).
- Clone failures on re-run → idempotent: `20_clone_corpus.py` skips existing
  clones and only reports the remainder.
- `--auto` finds nothing → the inventory is stale; re-run `40_inventory.py`.
