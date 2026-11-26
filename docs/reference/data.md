# Runtime inputs

[operator_config.yaml](../../data/operator_config.yaml) is the versioned
runtime configuration. The loader rejects unknown keys. Paths resolve
relative to the project root.

| Setting | Purpose |
| --- | --- |
| `github_user` and `include_forks` | Account to enumerate and whether to include its forks |
| `repos_dir` | Local clone directory, excluded from version control |
| `clone_workers`, `fetch_workers`, `run_workers` | Parallelism for clone, verification, and run stages |
| `run_timeout_s` and `stream_tail_bytes` | Per-repository timeout and retained output tail |
| `cma_dir` | Path binding for the separately installed optional CMA lane |

[claim_ledger.yaml](../../data/claim_ledger.yaml) records manuscript claim
evidence. Runtime snapshots and generated reports live in `output/`. See
the [evidence guide](../evidence.md) for how to interpret them.
