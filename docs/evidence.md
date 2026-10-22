# Evidence and Sidecar boundaries

This repository orchestrates and interprets a GitHub corpus. Within the DAF
stack, `daf-dot` owns the real-time voice protocol and `daf-operator` presents
spatialized information. This component supplies corpus artifacts and native
source qualification; it does not grant dispatch or execution authority to
either consumer.

| Evidence | Producer / reader | Meaning |
| --- | --- | --- |
| External scratch `source_gate.json` | `scripts/gate.sh` / `src/source_evidence.py` | Offline source qualification for the declared inputs at `generated_at` |
| `output/data/health_gate.json` | `scripts/70_health_gate.py` | Corpus artifact health; retained checkout outputs are historical until regenerated against the intended corpus |
| `.docxology/gate/gate_report.json` | Existing Flywheel tooling | Historical adoption report; retain its failed verdict, timestamp, checks, and provenance |
| Native Sidecar doctor / roster audit | `docxology-sidecar` | Sidecar configuration and observed coverage, with its own freshness and source binding |

## Source acceptance

Use the existing bound runtime, an external writable temporary directory, and
the repository lease described in GitVault's `docs/LOCKING.md`:

```sh
TMPDIR=/tmp bash scripts/gate.sh
```

An external runtime can be selected through `UV_PROJECT_ENVIRONMENT`; it must
already provide this project's dependencies. `--no-sync` preserves that
environment. The receipt records the actual Python executable/version and
checks the lock, but does not certify installed package versions match it.

The gate copies exactly `source_evidence.INPUT_DIRECTORIES` and `INPUT_FILES`,
verifies the copy, and retains `source_manifest.json` outside the checkout.
Those inputs include source, tests, scripts, documentation, configuration,
and saved data/figures. They exclude the fleet clones, Sidecar metadata, task
board, Git state, and unrelated root files. Added or removed declared input
files and permission changes invalidate the comparison. Symlink inputs are
refused, so an external checkout cannot enter through the saved inputs.

After preparing the snapshot, ordinary gate exits retain `source_gate.json`,
`pytest.xml`, and `coverage.json` where available. A failed subprocess, no
executed tests, unavailable evidence, insufficient coverage, or changed input
produces a failed source receipt and a nonzero exit. Process termination that
prevents the exit trap, or failure before snapshot preparation, may leave no
receipt; absence is unavailable evidence. Scratch token/figure regeneration
does not update the checkout's historical corpus outputs.

Before reusing a receipt, require `scope == "offline-source"`, `passed is True`,
the intended `source_root`, and the SHA-256 of the retained manifest matching
`source_manifest_sha256`. Compare its decoded list with
`to_dict(capture_inputs(source_root))` from `src/source_evidence.py`. Retain
the timestamp, runtime, and native evidence alongside the comparison. A
matching source receipt cannot establish current remote synchronization or
current corpus health. `tests/test_source_evidence.py` exercises changed,
missing, malformed, empty, failed, and insufficient evidence controls.

## Sidecar foothold

The plaintext `.docxology/manifest.toml` uses the existing eight-field native
schema and serializer. Blank owner and ORCID record unclassified identity;
the manifest grants no identity authority or Hum Lab affiliation. The retained
plain-mode v1 lock remains unchanged. No encryption, recipients, sealed files,
or credentials are introduced. `public/links.toml` is the native free-form
signpost surface.

From a workspace containing the canonical `Private/daf-sidecar` checkout:

```sh
bun run ../../Private/daf-sidecar/src/cli.ts doctor "$PWD" --json
```

The command returns the native `{status,data,error,meta}` envelope. Interpret
`data.verdict` independently: a dirty checkout is `concerns`, even when source
tests pass. Sidecar coverage's installed/configured/observed/validated/stale
fields describe its own bounded survey. Require its independent source/age
checks before reuse, as documented in Sidecar's `docs/coverage.md`. A plaintext
manifest and an empty sealed-files map do not prove Flywheel adoption or source
quality. Never initialize over retained locks or use empty locks as evidence.

## Integration next steps

Stack consumers can retain the source receipt and manifest paths without
replacing the native corpus or adoption reports. Resolve canonical stack paths
before invoking Flywheel: `.docxology/gate/config.json` still retains historical
paths under `/Volumes/external_drive`, which this source gate does not repair.
Rebind those paths through the owning tooling before a new adoption evaluation;
the existing failed report remains a historical observation.

To qualify live corpus output, use the intended installed clones and explicitly
run stages 30/40/60/70 with the required authorization. This offline gate does
not fetch or sync the corpus. Preserve per-repository `VerificationError`
rows and consumer state vocabularies when connecting results to the stack.
