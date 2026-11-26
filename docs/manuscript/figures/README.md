# Manuscript architecture figure

[Pipeline source](pipeline.mmd) and its [exported PNG](pipeline.png)
describe the registry, local Git verification and inventory, and artifact
consumers. Update the PNG from its Mermaid source when the diagram changes.
Mermaid CLI 12.2.0 and a compatible Chrome runtime were used for the export.

```sh
mmdc --input docs/manuscript/figures/pipeline.mmd --output docs/manuscript/figures/pipeline.png --scale 2
```

The [render command](../README.md#render-the-saved-manuscript) stages this
source asset alongside the saved corpus figures. The corpus figure generator
owns only the four `fig_*.png` analysis files.
