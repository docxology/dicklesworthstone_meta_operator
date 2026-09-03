# Standalone Fork Guide — dicklesworthstone_meta_operator

## Purpose

`dicklesworthstone_meta_operator` is a meta-operator over the
[Dicklesworthstone](https://github.com/Dicklesworthstone) GitHub corpus: clone
everything, verify upstream sync, orchestrate commands, interpret repos, and
render a dashboard. It lives in the private sidecar
(`projects/ongoing/Code_Tools/`) and is deliberately infrastructure-free:
unlike the exemplar it forked from, it imports nothing from the template
monorepo's `infrastructure/` — logging is stdlib, artifact I/O is `src/jsonio`,
and the subprocess boundaries are `gh` + `git`.

## Copy This When

You want a fleet operator over any GitHub user/org. Change
`data/operator_config.yaml` → `github_user`, re-run the pipeline.

## Clean Copy Command

Clone this repository and strip the corpus-specific state:

```bash
git clone https://github.com/docxology/dicklesworthstone_meta_operator.git my_fleet_operator
cd my_fleet_operator
rm -rf output/ && mkdir -p output/data output/reports output/web
```

(`repos/`, run artifacts, and caches are gitignored and never cloned.)

## Required Post-Fork Edits

- `pyproject.toml` (name/description), `data/operator_config.yaml` (target user),
  `README.md`, `AGENTS.md`, `docs/`, `experiment_plan.yaml`, `domain_profile.yaml`.
- The corpus-specific fixtures in `tests/` reference Dicklesworthstone only as
  fixture data — swap URLs/paths for your target account.

## What Not To Claim

Do not claim corpus-wide results (sync state, LOC, test outcomes) without
re-running stages 30/40 against a fresh registry — the artifacts are the only
evidence, and upstreams move daily.
