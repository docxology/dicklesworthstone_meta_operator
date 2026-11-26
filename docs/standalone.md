# Standalone checkout

Clone the repository and install the locked runtime and development
dependencies from the checkout root.

```sh
git clone https://github.com/docxology/dicklesworthstone_meta_operator.git
cd dicklesworthstone_meta_operator
uv sync --locked
```

The operator uses standard Python logging and its own artifact I/O. The
standalone runtime does not import the Template framework. The research
manuscript uses the separate [pinned Template renderer](manuscript/README.md).

The versioned [runtime input](../data/operator_config.yaml) controls the GitHub
account, clone location, fork inclusion, worker pools, timeouts, and output
capture. Existing outputs describe the account and date recorded in the
saved artifacts. A configuration change alone does not refresh them.

Follow the [offline workflow](README.md#use-the-saved-snapshot) for dashboard
and figure generation or the [source gate](evidence.md#source-acceptance) to
test the checkout against its local fixtures. Fleet discovery and refresh
have separate prerequisites and evidence, recorded in the
[pipeline reference](reference/scripts.md).
