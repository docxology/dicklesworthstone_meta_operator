# Manuscript — dicklesworthstone_meta_operator

Research manuscript for the meta-operator, artifact-backed end to end.
Rendering order: lexicographic by filename (`00_` abstract first, `99_`
references last).

| File | Content |
|---|---|
| `00_abstract.md` … `07_scope_and_related_work.md` | Sections (labels in [`SYNTAX.md`](SYNTAX.md)) |
| `99_references.md` + [`references.bib`](references.bib) | Pandoc–natbib bibliography |
| [`config.yaml`](config.yaml) | Paper metadata consumed by the renderer + token generator |
| [`preamble.md`](preamble.md) | LaTeX `header-includes` |
| [`SYNTAX.md`](SYNTAX.md) | Figure/equation/section/token registries |
| [`layer_contract.yaml`](layer_contract.yaml) | src/↔scripts/↔docs layer declarations |
| [`MANUSCRIPT_STATUS.md`](MANUSCRIPT_STATUS.md) | Live status |
| [`AGENTS.md`](AGENTS.md) | Agent protocol (token + figure discipline) |

Corpus measurements are hydrated from `output/data/manuscript_variables.json`.
The [figure generator](../../scripts/65_generate_figures.py) reads the saved
registry, inventory, and upstream reports. The [token cross-check](../../tests/test_manuscript_variables.py)
compares the generator and prose in both directions.

## Render the saved manuscript

Use [Template at the pinned commit](https://github.com/docxology/template/tree/87704feae0a4490ef7dad9c931d268e8c30273c2).
Install uv, Pandoc, a compatible pandoc-crossref, and XeLaTeX using the [Template run guide](https://github.com/docxology/template/blob/87704feae0a4490ef7dad9c931d268e8c30273c2/docs/RUN_GUIDE.md).
Register an indexed Git checkout at `projects/working/dicklesworthstone_meta_operator`,
as described in the [Template project guide](https://github.com/docxology/template/blob/87704feae0a4490ef7dad9c931d268e8c30273c2/projects/README.md).
For a sibling checkout named `dicklesworthstone_meta_operator`:

```sh
git clone https://github.com/docxology/template.git template
cd template
git checkout --detach 87704feae0a4490ef7dad9c931d268e8c30273c2
uv sync --locked --no-dev --python 3.14
mkdir -p projects/working
git -C ../dicklesworthstone_meta_operator worktree add --detach \
  "$PWD/projects/working/dicklesworthstone_meta_operator" HEAD
project=projects/working/dicklesworthstone_meta_operator
cp "$project/docs/manuscript/figures/pipeline.png" "$project/output/figures/"
cp "$project/docs/manuscript/figure_registry.json" "$project/output/figures/"
uv run --no-sync python - "$project" <<'PYTHON'
import json
import sys
from pathlib import Path
from infrastructure.rendering.manuscript_injection import write_resolved_manuscript_tree

project = Path(sys.argv[1]).resolve()
variables = json.loads((project / "output/data/manuscript_variables.json").read_text())
write_resolved_manuscript_tree(project, variables)
PYTHON
uv run --no-sync python scripts/pipeline/stage_03_render.py --project working/dicklesworthstone_meta_operator --skip-manuscript-hydration
uv run --no-sync python scripts/pipeline/stage_04_validate.py --project working/dicklesworthstone_meta_operator
```

The pinned hydration helper reads the canonical `docs/manuscript/` sources
and applies the tracked token map. The renderer then consumes the resolved
copy in `output/manuscript/` and the four corpus figures in `output/figures/`. The separately staged
[architecture diagram](figures/README.md) is a manuscript source asset.
The [figure registry](figure_registry.json) binds each label and image to
its alt text and producer.
The combined paper goes to
`output/pdf/dicklesworthstone_meta_operator_combined.pdf` and
`output/web/index.html` inside the registered checkout. Stage 04 writes
`output/reports/validation_report.json` and
`output/reports/rendered_provenance.json`.

The Stage 03 flag uses the prepared manuscript and preserves the saved
token map. To reproduce the saved ages from the same artifacts, run this in
a disposable checkout. The timestamp is the recorded time of the commit that
regenerated the two staleness tokens.
[Regeneration commit](https://github.com/docxology/dicklesworthstone_meta_operator/commit/d61b92d4fd92d2ce7c7b83f6a63f47f1cd174e7b)

```sh
uv run python scripts/z_generate_manuscript_variables.py --as-of 2026-11-04T00:25:42Z
```

For fresh tokens, omit `--as-of` to measure against the current time.
