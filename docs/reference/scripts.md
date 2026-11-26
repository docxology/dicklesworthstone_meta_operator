# scripts/ — Pipeline Stages

Thin orchestrators, numbered in pipeline order. Each script: argv parsing +
delegation to `src/` + artifact writes. No business logic — the boundary test
is in [layer contract](../../AGENTS.md).

| Script | Stage | Reads | Writes | Exit 1 when |
| --- | --- | --- | --- | --- |
| `00_preflight.py` | env check | — | — | toolchain/prereq missing (`--offline` skips gh auth) |
| `10_build_registry.py` | registry | GitHub API | `output/data/repo_registry.json` | gh/API failure |
| `20_clone_corpus.py` | clone | registry | `repos/`, `output/data/clone_outcomes.json` | any clone failed/mismatch |
| `30_verify_upstream.py` | verify | registry | `output/data/upstream_status.json` | any repo not upstream-ok (default **smart mode**: offline pass + `ls-remote` tip probe, fetching only drifted repos; `--full-fetch` fetches everything, `--no-fetch` is fully offline) |
| `40_inventory.py` | inventory | registry | `output/data/inventory.json` | clones missing |
| `50_orchestrate.py` | run | inventory + registry | `output/data/runs/<id>/results.json`, `output/reports/<id>.md` | any run failed/timed out |
| `60_dashboard.py` | dashboard | registry + status + inventory + runs | `output/web/dashboard.html`, `output/data/corpus_catalog.md` | registry missing |
| `65_generate_figures.py` | figures | registry + status + inventory | `output/figures/fig_*.png` (4) | required artifact missing |
| `70_health_gate.py` | gate | everything | `output/data/health_gate.json` | any gate check failed |
| `z_generate_manuscript_variables.py` | tokens | all artifacts | `output/data/manuscript_variables.json` | required artifact missing (strict mode) |
| `90_sync_corpus.py` | sync | registry | `output/data/runs/<id>/results.json` | any pull failed/timed out |

## Running stages

The [snapshot quickstart](../README.md#use-the-saved-snapshot) uses saved
inputs for the dashboard and figures. Stage 30 can read only the local
checkout and tracking references with `--no-fetch`. Its default mode checks
remote tips and may update local tracking references. Stage 40 reads the
local clone contents. Stages 20 and 90 write to local fleet clones. The
optional Stage 50 executes commands in selected local checkouts, so its
results and side effects depend on the commands and checkout contents.

The [offline source gate](../evidence.md#source-acceptance) verifies these
boundaries with local fixtures. It does not require current upstream data.
