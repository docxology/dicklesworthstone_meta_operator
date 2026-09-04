# scripts/ — Pipeline Stages

Thin orchestrators, numbered in pipeline order. Each script: argv parsing +
delegation to `src/` + artifact writes. No business logic — the boundary test
is in `../AGENTS.md`.

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

## Usage

From the template monorepo root:

```bash
uv run python projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/scripts/50_orchestrate.py --auto test --language Python --limit 5
```

or from the project directory:

```bash
uv run python scripts/50_orchestrate.py --command "git log -1 --format=%h %s"
```

## Orchestration selectors (50_orchestrate)

`--set N1 N2` explicit names · `--language` primary language · `--min-loc` ·
`--exclude` · `--limit` · `--sort name|size|loc|recent` · `--no-forks` · `--command "argv"`
(mutually exclusive with) `--auto test|lint|typecheck` (per-repo auto-detected
command; repos without one are skipped with a printed list).

## Testing

Script smoke tests live in `../tests/test_scripts_smoke.py` (preflight
`--offline` subprocess run + compile checks). All script behavior is covered
through the `src/` modules they delegate to.
