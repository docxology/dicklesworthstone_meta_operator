# src/ — Operator Logic

Importable project logic. Four frozen contract modules (models, jsonio,
config, project_paths) plus thirteen workflow/boundary modules (github_client,
git_probe, registry, cloner, upstream_check, inventory, orchestrator, cma_lane,
dashboard, figures, manuscript_variables, health_gate, source_evidence —
workflow modules never import each other; they communicate through JSON
artifacts under `output/data/`).

## Modules

| Module | Responsibility | Boundary |
| --- | --- | --- |
| `models.py` | Dataclasses + state vocabularies + `to_dict`/`from_dict` | Pure stdlib |
| `jsonio.py` | Atomic JSON/text I/O, strict required reads | stdlib only |
| `config.py` | Typed `operator_config.yaml` loader, unknown-key rejection | yaml |
| `project_paths.py` | Project root, output dirs, artifact filenames | stdlib only |
| `github_client.py` | Repo enumeration via `gh api --paginate` (subprocess); pure parsing | subprocess `gh` |
| `git_probe.py` | Explicit-checkout `git` probes shared by inventory + upstream verification | subprocess `git` |
| `registry.py` | Registry artifact build/save/load/diff | jsonio |
| `cloner.py` | Idempotent parallel clone planning + execution | subprocess `git` |
| `upstream_check.py` | Per-clone upstream-default verification, state machine | subprocess `git` |
| `inventory.py` | Per-repo interpretability profiles | fs walk + `git log` |
| `orchestrator.py` | Selector-filtered command runs + reports | subprocess |
| `cma_lane.py` | code_meta_analysis lane (`--auto cma-analyze`): issues + deps per repo | subprocess `uv run` in the cma checkout |
| `dashboard.py` | Self-contained HTML dashboard + markdown catalog (pure renderers) | none (pure) |
| `health_gate.py` | Binary go/no-go over the artifact tree (incl. figures + token map) | jsonio reads |
| `figures.py` | Deterministic manuscript figure builders (pure, colorblind-safe) | matplotlib (Agg) |
| `manuscript_variables.py` | `{{TOKEN}}` generator: tracked artifacts → prose token map | jsonio + config |
| `source_evidence.py` | Verified gate snapshots, input manifests, source receipts | filesystem + jsonio; GateCheck/GateReport |

## API Reference

Signatures are documented in each module's docstrings; the artifact shapes are
fixed in `../docs/architecture.md`. Key entry points:

- `github_client.enumerate_repos(user, *, include_forks, runner=None) -> list[RepoMeta]`
- `registry.build_registry / save_registry / load_registry / registry_metas`
- `cloner.plan_clones / execute_plan / clone_corpus`
- `upstream_check.verify_one / verify_all / build_report`
- `inventory.profile_repo / build_inventory`
- `orchestrator.SelectorSpec / filter_repos / execute_runs / run_and_save / summarize / render_run_report`
- `dashboard.load_payload / compute_summary / render_dashboard / render_catalog / write_artifacts`
- `health_gate.run_gate / save_gate / load_gate`

## Rules

- No `infrastructure.*` imports (this fork is infrastructure-free by design —
  see `../STANDALONE.md`).
- No `print()` — `logging.getLogger(__name__)`.
- Every subprocess failure becomes a typed outcome, never an unhandled crash
  inside batch loops; genuinely unexpected errors raise with context.
- Full type hints + docstrings on public API; deterministic ordering in all
  serialized output.
