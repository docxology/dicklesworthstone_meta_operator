# dicklesworthstone_meta_operator TODO

Future-only backlog. Every active row needs a stable ID, size, dependency, next
action, proving artifact, acceptance command, and negative control. Rows stay
active until the acceptance command and negative control pass in the same
source revision.

## Current pipeline state

- Full corpus (207 repos) cloned into `repos/`; registry, upstream status,
  inventory, dashboard, and gate artifacts generated. Re-run stages 30/40/60/70
  after any corpus change — all idempotent.
- First adversarial review (3 lenses + refutation pass) closed 16 findings.

Delivered 2026-09-03 (v0.2.0): OPS-1 `scripts/90_sync_corpus.py` (with
`--submodules`, OPS-3), OPS-2 `--no-forks` selectors, OPS-4 smart fetch
(offline pass + `ls-remote` tip probe), OPS-5 per-repo run history in the
dashboard drawer.

## Minor upcoming

| ID | Status | Size | Dependency | Next action / unblock condition | Proving artifact | Acceptance command | Negative control |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OPS-1 | open | S | none | Add `scripts/90_sync_corpus.py` (fetch + `git pull --ff-only` across the corpus) so stage 30 stops being the sync mechanism | `output/data/runs/<id>/results.json` with zero failed pulls | `uv run python scripts/90_sync_corpus.py && uv run python scripts/30_verify_upstream.py` | A repo with a diverged upstream keeps state `diverged` and fails the gate |
| OPS-2 | open | S | none | Expose `--include-forks/--no-forks` on script 50/60 selectors instead of config-only | `--help` output showing the flag | `uv run python scripts/50_orchestrate.py --auto test --no-forks --set <fork-repo>` excludes it | Fork repos still selectable when the flag is omitted |
| OPS-3 | open | S | OPS-1 | Per-repo `git submodule update --init` option for orchestrator runs | runs artifact recording submodule status | select a repo with submodules, assert success | Repos without `.gitmodules` skip cleanly |

## Medium upcoming

| ID | Status | Size | Dependency | Next action / unblock condition | Proving artifact | Acceptance command | Negative control |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OPS-4 | open | M | none | Incremental verify: skip repos whose `origin/<default>` sha is unchanged since the last artifact (hash the state) | verify wall-clock drop on second run | run 30 twice; second run reports cache hits | A repo with a moved upstream is always re-verified |
| OPS-5 | open | M | none | Language-aware test triage in the dashboard: surface per-repo auto_cmds success history from runs artifacts | dashboard runs panel per repo | run tests twice, open dashboard, see history | No runs → panel shows "no runs yet" |

## Blocked

| ID | Status | Size | Dependency | Next action / unblock condition | Proving artifact | Acceptance command | Negative control |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OPS-6 | blocked | M | upstream API | Stargazer/activity trend capture needs a higher gh rate budget than the operator should assume | — | — | — |

## Backlog status

A blocked row is a deliberate boundary, not a skipped success.
