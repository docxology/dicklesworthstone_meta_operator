# Corpus operator Sidecar foothold

`manifest.toml` is native plaintext metadata. Owner/ORCID are unclassified;
empty affiliation fields establish no identity or project affiliation. The
existing `.sidecar-lock.toml` is retained without changes.

Source acceptance is `bash scripts/gate.sh` with an external `TMPDIR` and an
existing bound runtime. Its receipts remain in scratch, linked by the command
output. See [evidence boundaries](../docs/evidence.md) and
[public signposts](public/links.toml).

`gate/gate_report.json` is historical Flywheel evidence with its original
failed verdict. Its config retains paths from an earlier checkout; a new
source pass cannot refresh or replace that adoption result. Native Sidecar
doctor/coverage is another independent observation. A dirty working tree
remains `concerns`, not validated.
