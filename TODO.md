# dicklesworthstone_meta_operator task index

The canonical task records are in [tasks.yaml](tasks.yaml). Follow the linked IDs
for current status, dependencies, acceptance criteria, prompts and owner holds.
This view records no independent task state. Preserve blocked and completed records.

Native contracts: [AGENTS.md](AGENTS.md). Task and gate signposts:
[public/links.toml](.docxology/public/links.toml). Resolve ecosystem members from
`daf_stack.manifest.default_manifest()`; Flywheel proposals and Horizon previews
remain subject to Operator policy, source freshness and separate execution admission.

- [dmo-6](tasks.yaml#L14) — Source-bound offline gate evidence and Sidecar foothold
- [dmo-1](tasks.yaml#L36) — Adopt flywheel scaffolding (board, beads, plan, gate)
- [dmo-2](tasks.yaml#L59) — Reconcile OPS backlog truth (run OPS-1..3 acceptance commands)
- [dmo-3](tasks.yaml#L83) — OPS-4 incremental upstream verify (cache unchanged origin tips)
- [dmo-4](tasks.yaml#L107) — Corpus-scale cma integration lane and dashboard panel
- [dmo-5](tasks.yaml#L138) — Flywheel adoption review hardening round

## Retained notes

The following material is preserved verbatim as historical context. Its checkboxes,
status labels, counts and suggestions are not a current queue or validation receipt.
Unmapped suggestions require owner reconciliation against canonical task IDs before work.
Read the board above for current state; these notes grant no dispatch authority.

---

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
| OPS-1 | done | S | none | Add `scripts/90_sync_corpus.py` (fetch + `git pull --ff-only` across the corpus) so stage 30 stops being the sync mechanism | `output/data/runs/<id>/results.json` with zero failed pulls | `uv run python scripts/90_sync_corpus.py && uv run python scripts/30_verify_upstream.py` | A repo with a diverged upstream keeps state `diverged` and fails the gate |
| OPS-2 | done | S | none | Expose `--include-forks/--no-forks` on script 50/60 selectors instead of config-only | `--help` output showing the flag | `uv run python scripts/50_orchestrate.py --auto test --no-forks --set <fork-repo>` excludes it | Fork repos still selectable when the flag is omitted |
| OPS-3 | done | S | OPS-1 | Per-repo `git submodule update --init` option for orchestrator runs | runs artifact recording submodule status | select a repo with submodules, assert success | Repos without `.gitmodules` skip cleanly |

## Medium upcoming

| ID | Status | Size | Dependency | Next action / unblock condition | Proving artifact | Acceptance command | Negative control |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OPS-4 | done | M | none | Incremental verify: skip repos whose `origin/<default>` sha is unchanged since the last artifact (prev-tips cache; `--no-cache` escape) | run 2 over the live 207-repo corpus: 145/207 cache hits; moved tips re-verified (mutation test in tests/test_upstream_check.py, 22 pass) | run 30 twice; second run reports cache hits | A repo with a moved upstream is always re-verified |
| OPS-5 | open | M | none | Language-aware test triage in the dashboard: surface per-repo auto_cmds success history from runs artifacts | dashboard runs panel per repo | run tests twice, open dashboard, see history | No runs → panel shows "no runs yet" |

## Source evidence and Sidecar

| ID | Status | Size | Dependency | Next action / unblock condition | Proving artifact | Acceptance command | Negative control |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OPS-7 | done | S | existing offline gate | Retain a verified scratch snapshot with source-bound GateReport checks; use `docs/evidence.md` reuse checks before integration | External `source_gate.json`, `source_manifest.json`, `pytest.xml`, `coverage.json`; `docs/evidence.md` | `TMPDIR=/tmp bash scripts/gate.sh` with the existing bound runtime | `pytest tests/test_source_evidence.py`: changed source, empty execution, malformed evidence, low/line-only coverage and nonzero process must fail |

## Blocked dependencies

| ID | Status | Size | Dependency | Next action / unblock condition | Proving artifact | Acceptance command | Negative control |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OPS-6 | blocked | M | upstream API | Stargazer/activity trend capture needs a higher gh rate budget than the operator should assume | — | — | — |

## Backlog status

A blocked row is a deliberate boundary, not a skipped success.
