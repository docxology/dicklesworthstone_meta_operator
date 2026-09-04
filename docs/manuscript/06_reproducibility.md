# Reproducibility Certification {#sec:reproducibility}

## The token discipline {#sec:token-discipline}

Every numeric claim in this manuscript is an uppercase token registered (`src/manuscript_variables.py::generate_variables`) and cross-checked in both directions by one test (`tests/test_manuscript_variables.py`):

- **No invented numbers.** A token used in prose that the generator does not emit fails the suite — prose cannot reference evidence that does not exist.
- **No stale evidence.** A token the generator emits but the prose never uses fails the suite — a generator cannot claim to support claims the document no longer makes.

The generator reads only tracked artifacts (registry, upstream status, inventory, health gate) plus the manuscript configuration, so any edit to the corpus or the prose that breaks correspondence is caught by CI. The exact token map used to hydrate this document is tracked at `output/data/manuscript_variables.json`.

## Artifact integrity {#sec:artifact-integrity}

Each consumed artifact is pinned by the first eight hex characters of its SHA-256:

| Artifact | SHA-256 prefix |
|---|---|
| `output/data/repo_registry.json` | `{{ARTIFACT_SHA8_REGISTRY}}` |
| `output/data/upstream_status.json` | `{{ARTIFACT_SHA8_UPSTREAM}}` |
| `output/data/inventory.json` | `{{ARTIFACT_SHA8_INVENTORY}}` |

The verification snapshot itself is stamped {{VERIFY_GENERATED_AT}}. The health-gate artifact is deliberately not hash-pinned here: its content depends on figure presence, and the figures are regenerated in the same pipeline that hydrates this document — the gate is a *derived verdict*, not input evidence. Re-running the pipeline stages (10 → 90) regenerates every artifact; re-running `scripts/65_generate_figures.py` regenerates all {{FIGURE_COUNT}} manuscript figures from the same inputs deterministically (fixed palette, sorted inputs, no embedded timestamps).

## Test discipline {#sec:test-discipline}
The suite spans {{FIGURE_COUNT}}+ figure, gate, inventory, orchestration, dashboard, and contract tests — 180 at the time of writing — with zero mocks: no `unittest.mock`, `MagicMock`, `@patch`, or `create_autospec` anywhere in `tests/`. Git behavior is tested against real fixture repositories built by `git init`/`commit`/`push` in temporary directories; the GitHub boundary is exercised through a real PATH-stubbed `gh` executable that emits fixture pages; figure code is tested by generating real PNGs and asserting byte-identical determinism. Branch coverage on `src/` is gated at ≥90 % (achieved: 94 %+) and enforced both locally and in CI on Python 3.11, 3.12, and 3.13, which also regenerates the figures from the tracked artifacts on every push.

## Reproducing the snapshot {#sec:reproducing}

From a clone of the repository:

```bash
uv run python scripts/10_build_registry.py     # GitHub API -> registry
uv run python scripts/20_clone_corpus.py       # idempotent parallel clone (~10 GB)
uv run python scripts/30_verify_upstream.py    # smart-fetch verification
uv run python scripts/40_inventory.py          # interpretability profiles
uv run python scripts/65_generate_figures.py   # manuscript figures
uv run python scripts/60_dashboard.py          # dashboard + catalog
uv run python scripts/70_health_gate.py        # binary gate
uv run python scripts/z_generate_manuscript_variables.py
```

All stages are idempotent; a stage that cannot verify prints a fix hint and exits non-zero. The manuscript numbers will then be *this* run's numbers, and the token test will confirm the prose still tracks them.