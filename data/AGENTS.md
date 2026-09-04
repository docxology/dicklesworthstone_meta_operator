# Data Directory — Agent Guide

Versioned project **inputs** only. Generated artifacts live under `output/` and
are disposable.

## `operator_config.yaml`

The single runtime configuration input: `github_user`, `repos_dir`,
`include_forks`, worker counts, per-run timeout, stream tail size. Loaded by
`src/config.load_config` with typed defaults; **unknown keys are a hard error**
(a typo must not be silently ignored).

## `claim_ledger.yaml`

Evidence-registry for manuscript claims that are intentionally sourced from
code, external receipts, or generated reports rather than `{{TOKEN}}` injection
(those live in `output/data/manuscript_variables.json`).

### Schema (preserve when adding rows)

| Field | Purpose |
| --- | --- |
| `claim_id` | Stable identifier |
| `kind` | Claim category |
| `value` | Declared value |
| `source` | Provenance (module, manuscript section, artifact, external receipt) |
| `source_tier` | Trust tier for validation |
| `freshness` | Staleness policy |
| `artifact_path` | Optional path to backing file |

## Edit protocol

1. Edit only when manuscript claims, operator configuration, or source-backed
   facts change.
2. Re-run the validation stages that consume the ledger (token cross-check,
   health gate).
3. Do not store generated CSV/JSON/PNG under `data/` — that is what `output/`
   is for.

Quick orientation: [`README.md`](README.md).