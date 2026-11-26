# Reproducibility Certification {#sec:reproducibility}

## The token discipline {#sec:token-discipline}

Reported corpus measurements use uppercase tokens registered (`src/manuscript_variables.py::generate_variables`) and cross-checked in both directions by one test (`tests/test_manuscript_variables.py`):

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

The verification snapshot itself is stamped {{VERIFY_GENERATED_AT}}. The health-gate artifact is deliberately not hash-pinned here: its content depends on figure presence, and the figures are regenerated in the same pipeline that hydrates this document — the gate is a *derived verdict*, not input evidence. The corpus refresh stages produce a new observation. Re-running `scripts/65_generate_figures.py` regenerates all {{FIGURE_COUNT}} manuscript figures from the same inputs deterministically (fixed palette, sorted inputs, no embedded timestamps).

## Test discipline {#sec:test-discipline}
The suite covers figures, gate decisions, inventory, orchestration, dashboards, and shared contracts. Its zero-mock rule prohibits no `unittest.mock`, `MagicMock`, `@patch`, or `create_autospec` anywhere in `tests/`. Git behavior is tested against real fixture repositories built by `git init`/`commit`/`push` in temporary directories; the GitHub boundary is exercised through a real PATH-stubbed `gh` executable that emits fixture pages; figure code is tested by generating real PNGs and asserting byte-identical determinism. Branch coverage on `src/` is gated at ≥90 % and enforced both locally and in CI against the configured Python matrix. The CI workflow also generates the figures from the tracked artifacts.

## Reproducing the snapshot {#sec:reproducing}

The checkout retains the registry, upstream status, inventory, gate report,
token map, and figures used to render the captured results. The dashboard
and figures can be regenerated from those local inputs:

```bash
uv sync --locked
uv run --locked python scripts/60_dashboard.py
uv run --locked python scripts/65_generate_figures.py
```

The saved token map preserves the snapshot's staleness values. The native
source gate tests regeneration in a scratch copy, where the current date
affects those values. A new corpus refresh constitutes a new observation.
