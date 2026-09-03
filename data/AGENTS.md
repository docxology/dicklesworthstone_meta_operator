# Data Directory — Agent Guide

Versioned project **inputs** only. Generated artifacts live under `output/` and
are disposable.

## `operator_config.yaml`

The single runtime configuration input: `github_user`, `repos_dir`,
`include_forks`, worker counts, per-run timeout, stream tail size. Loaded by
`src/config.load_config` with typed defaults; **unknown keys are a hard error**
(a typo must not be silently ignored).

## Edit protocol

1. Edit only when the operator's target or resource budget changes.
2. Re-run the affected stages after changing anything the stages consume.
3. Never store generated CSV/JSON/PNG under `data/` — that is what `output/`
   is for (and the health gate would still call the pipeline incomplete).

Quick orientation: [`README.md`](README.md).
