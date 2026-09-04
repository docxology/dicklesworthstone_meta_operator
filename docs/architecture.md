# Architecture

## Layers

```
scripts/00-70 (thin: argv + delegation + writes)
      │
src/github_client.py ── gh CLI (subprocess)      src/registry.py ── repo_registry.json
src/cloner.py        ── git clone (subprocess)   output/data/clone_outcomes.json
src/upstream_check.py── git fetch/rev-parse      output/data/upstream_status.json
src/inventory.py     ── filesystem walk + git log output/data/inventory.json
src/orchestrator.py  ── subprocess runs          output/data/runs/<id>/results.json
src/dashboard.py     ── pure render              output/web/dashboard.html + corpus_catalog.md
src/health_gate.py   ── reads everything         output/data/health_gate.json
      │
src/models.py (vocabularies, dataclasses, to_dict/from_dict)
src/jsonio.py (atomic JSON/text I/O)   src/config.py (operator_config.yaml)
src/project_paths.py (root, dirs, filenames)
```

Import rule: workflow modules may import the four contract modules; they never
import each other. Cross-module communication happens through the JSON
artifacts (below) — this is what keeps every module independently testable
and the pipeline stages re-runnable in any order.

## Artifact contract (exact shapes)

| Artifact | Shape |
| --- | --- |
| `output/data/repo_registry.json` | `{"generated_at", "github_user", "include_forks", "repos": [RepoMeta…]}` |
| `output/data/clone_outcomes.json` | `{"generated_at", "status_counts", "failed": [CloneOutcome…], "repos": [CloneOutcome…]}` |
| `output/data/upstream_status.json` | `{"generated_at", "checked", "ok", "repos": [UpstreamStatus…]}` (name-sorted) |
| `output/data/inventory.json` | `{"generated_at", "repos": [RepoProfile…], "missing": [names]}` (name-sorted) |
| `output/data/runs/<run_id>/results.json` | `{"run_id", "generated_at", "command", "selector", "repos": [RunResult…]}` (name-sorted) |
| `output/data/health_gate.json` | `{"generated_at", "passed", "checks": [GateCheck…]}` |
| `output/figures/fig_*.png` (4) | deterministic manuscript figures (`src/figures.py` via script 65) |
| `output/data/manuscript_variables.json` | `{{TOKEN}}` map for the manuscript (one generator, dual-direction test) |

State vocabularies live in `src/models.py` (single source of truth):
`CloneOutcome.status` ∈ {cloned, already_cloned, failed, mismatch};
`UpstreamStatus.state` ∈ {on_upstream, behind, ahead, diverged, dirty,
detached, off_default, unborn, missing}; OK-for-gate = {on_upstream, unborn};
`AUTO_COMMAND_KEYS` = {test, lint, typecheck}.

## Upstream verification model

`verify_one(repo, default_branch)` classifies in a fixed order: unborn →
detached → dirty → fetch → branch comparison → ahead/behind via
`git rev-list --left-right --count HEAD...origin/<default>`. The health gate
passes only `on_upstream` and `unborn` states; `missing` (upstream default ref
unresolvable after fetch) fails the gate. Batch verification defaults to
**smart fetch** (`verify_all(..., smart_fetch=True)`): an offline pass over
cached refs first, then a cheap `git ls-remote` tip probe for clean repos, and
full fetch + re-verification only for repos that are not cleanly synced or
whose remote tip moved — a synced corpus costs probes, not fetches.

## Dashboard

`render_dashboard(payload, summary)` is a pure function: one self-contained
HTML string (inline CSS + vanilla JS, zero network, deterministic ordering,
HTML-escaped repo-derived text). `render_catalog` is the markdown twin.
Both are tested for XSS-escaping and determinism.
