# Architecture

## Layers

```
scripts/00-90 + z_ token generator (thin: argv + delegation + writes)
      │
src/github_client.py ── gh CLI (subprocess)      src/registry.py ── repo_registry.json
src/cloner.py        ── git clone (subprocess)   output/data/clone_outcomes.json
src/upstream_check.py── git fetch/rev-parse      output/data/upstream_status.json
src/inventory.py     ── filesystem walk + git log output/data/inventory.json
src/cma_lane.py      ── cma lanes CLI (uv run)   output/data/runs/<id>/results.json ("cma" key) + output/data/cma/<id>/
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

The retained CMA lane is an explicit composition of orchestration helpers:
stage 50 accepts `--auto cma-analyze` and delegates to `run_cma_analyze`.
`OperatorConfig.cma_dir` resolves relative to the project root; `--cma-dir`
overrides it for a detached worktree. It must identify the CMA checkout's
`scripts/lanes.py`. Child lanes clear the caller's `UV_PROJECT_ENVIRONMENT`,
`UV_PYTHON`, `UV_PROJECT`, `UV_WORKING_DIRECTORY`, and `VIRTUAL_ENV`; CMA selects
its own project and interpreter while retaining external cache and temporary
storage bindings. Standalone test projects declare their metadata and Python
selection, preventing discovery of a containing management project.
The lane runs issues and dependencies per selected repo,
records failures in its existing `cma` rows, and preserves the ordinary
`AUTO_COMMAND_KEYS` vocabulary for repository-detected commands.

Native upstream probes resolve the selected checkout before binding its `.git`
marker and clear inherited Git selectors. Relative paths and linked worktrees
retain their identity; stray directories cannot borrow an ancestor checkout.
`git_probe.DEFAULT_TIMEOUT_SECONDS` is the per-process limit (60 seconds);
real slow-executable tests shorten that constant without replacing subprocesses.
`run_git` returns exit 124 on timeout. The single-repo verifier raises a typed
`GitProbeTimeout`; batch verification records a `VerificationError` and continues
the other requests, including cached, parallel-fetch and smart-tip paths.
Offline test smoke writes and bytecode go into real temporary fixtures.
`scripts/gate.sh` copies the complete source, tests, documentation and required
saved inputs into external scratch, regenerates the token map there with the
real strict generator, then runs the unchanged full coverage suite and figure
generation against that snapshot. This isolates clock-dependent staleness
tokens and generated diagnostics from the source checkout. Runtime dependencies
remain in the existing bound environment; no new environment is created.
This source qualification does not synchronize a live corpus or qualify its
historical generated outputs for integration. Canonical manuscript variables
and live health artifacts require regeneration in a separately reviewed context.

`src/source_evidence.py` owns the gate's declared input manifest and verified
copy. It rejects symlinks, compares content hashes and permission bits, and
never traverses `repos/`. After snapshot preparation, the shell's exit trap
retains a source receipt for successful and failed runs. Its checks require
the entire gate's zero exit, executed JUnit cases without failures/errors,
branch measurement meeting the coverage threshold, and original inputs still
matching the snapshot. Consumers must recompare inputs before receipt reuse;
the runtime executable/version and observation timestamp remain evidence,
not an assertion of installed dependency parity. See [evidence.md](evidence.md).

## Artifact contract (exact shapes)

| Artifact | Shape |
| --- | --- |
| `output/data/repo_registry.json` | `{"generated_at", "github_user", "include_forks", "repos": [RepoMeta…]}` |
| `output/data/clone_outcomes.json` | `{"generated_at", "status_counts", "failed": [CloneOutcome…], "repos": [CloneOutcome…]}` |
| `output/data/upstream_status.json` | `{"generated_at", "checked", "ok", "repos": [UpstreamStatus or VerificationError…]}` (name-sorted) |
| `output/data/inventory.json` | `{"generated_at", "repos": [RepoProfile…], "missing": [names]}` (name-sorted) |
| `output/data/runs/<run_id>/results.json` | `{"run_id", "generated_at", "command", "selector", "repos": [RunResult…]}` (name-sorted); cma runs add `"cma": {repo: {issues_count, central_file, coupling, lanes: {issues, deps}, status}}` |
| `output/data/health_gate.json` | `{"generated_at", "passed", "checks": [GateCheck…]}` |
| `output/figures/fig_*.png` (4) | deterministic manuscript figures (`src/figures.py` via script 65) |
| `output/data/manuscript_variables.json` | `{{TOKEN}}` map for the manuscript (one generator, dual-direction test) |
| `output/data/cma/<run_id>/<repo>_issues.json` | cma `issues` lane report per repo (written by the cma checkout, kept for inspection) |
| External gate scratch `source_manifest.json` | name-sorted `[{path: relative input filename, sha256: content hash, mode: permission bits}]` |
| External gate scratch `source_gate.json` | `{generated_at, passed, checks: [GateCheck…], scope: "offline-source", source_root, source_manifest, source_manifest_sha256, python_executable, python_version}`; no corpus/Sidecar/adoption verdict |
| External gate scratch `pytest.xml`, `coverage.json` | Native pytest JUnit and coverage.py JSON evidence; neither replaces an overall source verdict |

State vocabularies live in `src/models.py` (single source of truth):
`CloneOutcome.status` ∈ {cloned, already_cloned, failed, mismatch};
`UpstreamStatus.state` ∈ {on_upstream, behind, ahead, diverged, dirty,
detached, off_default, unborn, missing}; OK-for-gate = {on_upstream, unborn};
`AUTO_COMMAND_KEYS` = {test, lint, typecheck}.

`cma` run rows additionally carry lane statuses ∈ {ok, failed} per lane
(`issues`, `deps`); a repo with no cma report is absent from the `cma` map and
renders "no cma report yet" in the dashboard panel. The cma checkout path is
`OperatorConfig.cma_dir` (default `../code_meta_analysis`, resolved relative
to the project root).

`models.VerificationError` (also exported by `upstream_check`) is a separate batch outcome, not an
`UpstreamStatus` classification. Its row contains `name`, `default_branch`,
`state: "error"`, and the actual `error` diagnostic; it has no invented branch,
SHA, ahead/behind counts or flags. It counts toward `checked`, never `ok`.
The existing health gate refuses this state and the dashboard renders it red.
Its read-only `cache_hit` property is always false, preserving the stage-30
cache summary API without adding fabricated classification fields to JSON.

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
