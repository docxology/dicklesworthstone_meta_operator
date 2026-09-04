# Manuscript Syntax Reference (dicklesworthstone_meta_operator)

Project-specific overlay on the canonical manuscript semantics — this file documents the **meta-operator**-specific figure registry, equation labels, section labels, and the token table.

## Citation Syntax (Pandoc)

```markdown
[@docxology2026template]            <!-- single -->
[@docxology2026template; @chacon2014progit]  <!-- multiple -->
@chacon2014progit showed that...    <!-- narrative -->
```

All keys must exist in [`references.bib`](references.bib). Never write raw `\cite{}` in Markdown.

## Equation label registry

| Label | Formalism | Source file |
|---|---|---|
| `{#eq:sync_ratio}` | Primary metric: fraction of corpus in $\mathcal{OK}$ | `01_introduction.md` |
| `{#eq:state_machine}` | Priority-ordered nine-state upstream classification | `02_methodology.md` |
| `{#eq:loc_count}` | Bounded source-line counting $L(r)$ | `02_methodology.md` |
| `{#eq:gate}` | Binary health gate as conjunction of checks | `02_methodology.md` |
| `{#eq:staleness}` | Repository age $\Delta_r$ | `03_results.md` |

## Figure label registry

| Label | PNG filename | Generator (`src/figures.py`, orchestrated via `scripts/65_generate_figures.py`) |
|---|---|---|
| `{#fig:states}` | `output/figures/fig_state_distribution.png` | `build_state_distribution_figure()` |
| `{#fig:languages}` | `output/figures/fig_language_distribution.png` | `build_language_distribution_figure()` |
| `{#fig:loc_size}` | `output/figures/fig_loc_size.png` | `build_loc_size_figure()` |
| `{#fig:staleness}` | `output/figures/fig_staleness.png` | `build_staleness_figure()` |

Images live in `output/figures/` and are referenced as `../../output/figures/<name>.png`. Captions are self-contained. Figures are regenerated deterministically from tracked artifacts by `scripts/65_generate_figures.py`.

## Table label registry

| Label | Caption | Source file |
|---|---|---|
| `{#tbl:languages}` | Primary-language distribution | `03_results.md` |

## Section labels

| File | Section H1 | Label |
|---|---|---|
| `00_abstract.md` | Abstract | `{#sec:abstract}` |
| `01_introduction.md` | Introduction | `{#sec:introduction}` |
| `02_methodology.md` | Methodology | `{#sec:methodology}` |
| `03_results.md` | Results | `{#sec:results}` |
| `04_conclusion.md` | Conclusion | `{#sec:conclusion}` |
| `05_operational_setup.md` | Operational Setup | `{#sec:operational_setup}` |
| `06_reproducibility.md` | Reproducibility Certification | `{#sec:reproducibility}` |
| `07_scope_and_related_work.md` | Scope, Related Work, and Positioning | `{#sec:scope}` |
| `99_references.md` | References | `{#sec:references}` |

## Token registry

All tokens are emitted by `src/manuscript_variables.py::generate_variables` from tracked artifacts; the dual-direction cross-check (`tests/test_manuscript_variables.py`) enforces prose↔generator equivalence.

| Prefix | Source artifact | Tokens |
|---|---|---|
| `CONFIG_*` | `docs/manuscript/config.yaml` + registry | `CONFIG_TITLE`, `CONFIG_VERSION`, `CONFIG_KEYWORDS`, `CONFIG_GITHUB_USER` |
| `CORPUS_*` | registry + inventory | `CORPUS_REPO_TOTAL`, `CORPUS_FORK_TOTAL`, `CORPUS_ARCHIVED_TOTAL`, `CORPUS_LANG_COUNT`, `CORPUS_LANG1..5_NAME`, `CORPUS_LANG1..5_COUNT`, `CORPUS_LANG_OTHER_REPOS`, `CORPUS_TOTAL_LOC`, `CORPUS_TOTAL_SIZE_GB`, `CORPUS_WITH_TESTS`, `CORPUS_WITH_TESTS_PCT`, `CORPUS_CI_WORKFLOWS`, `CORPUS_CARGO_MANIFESTS`, `CORPUS_PYPROJECT_MANIFESTS`, `CORPUS_STALE_MAX_DAYS`, `CORPUS_STALE_MEDIAN_DAYS` |
| `VERIFY_*` | upstream_status.json | `VERIFY_TOTAL`, `VERIFY_ON_UPSTREAM`, `VERIFY_BEHIND`, `VERIFY_UNBORN`, `VERIFY_OTHER_NOT_OK`, `VERIFY_OK`, `VERIFY_OK_PCT`, `VERIFY_GENERATED_AT` |
| `GATE_*` / `FIGURE_*` | health_gate.json + figures | `GATE_VERDICT`, `GATE_CHECKS_TOTAL`, `GATE_CHECKS_PASSED`, `FIGURE_COUNT` |
| `ARTIFACT_SHA8_*` | file hashes | `ARTIFACT_SHA8_REGISTRY`, `ARTIFACT_SHA8_UPSTREAM`, `ARTIFACT_SHA8_INVENTORY`, `ARTIFACT_SHA8_GATE` |

**Edit protocol.** To change a number-bearing sentence, change the artifact-producing behavior, regenerate, and let the token test tell you which tokens changed. Never hand-write a number into prose; never hand-edit `output/data/manuscript_variables.json`.

## Prose conventions

- No "In summary"/"In conclusion" section closers (RASP standard)
- Explicit file paths for code references (`src/upstream_check.py`, not "the verification module")
- Active voice for methodology; one idea per paragraph
- Mermaid only for architecture/flow diagrams; matplotlib figures for data