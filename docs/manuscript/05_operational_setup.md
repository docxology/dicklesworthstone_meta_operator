# Operational Setup {#sec:operational_setup}

This section records the operational configuration under which the captured results were produced, and the infrastructure failure modes encountered while operating a ~{{CORPUS_TOTAL_SIZE_GB}} GB fleet on external storage — both are part of the system's evidence, not its appendix.

## Configuration surface {#sec:config-surface}

The operator's single runtime input is `data/operator_config.yaml`: the target user, clone directory, worker counts, per-run timeout, and captured stream tail size. The manuscript configuration (`docs/manuscript/config.yaml`) correlates the prose with the runtime input; both name {{CONFIG_GITHUB_USER}} as the corpus owner, with `include_forks: true` at capture time. Configuration loading is strict: unknown keys are a hard error, because a typo silently ignored is a generator failure masked.

## Unattended steady state {#sec:steady-state}

The full refresh chain — sync, verify, inventory, figures, dashboard, gate — runs daily as a scheduled job on the operator's host. The job is defensive by construction: it waits for storage availability, re-synchronizes the canonical tracked tree into the execution tree before running, retries each stage with backoff, mirrors fresh artifacts into the release clone, and pushes them when tracked artifacts changed. Silence is the success signal; failures surface through the run state.

## Real infrastructure failure modes {#sec:failure-modes}

Operating a {{CORPUS_REPO_TOTAL}}-repository fleet on consumer hardware surfaced three failure modes that now have typed remediations:

1. **Stale lock files.** A `git pull` killed mid-run leaves `ORIG_HEAD.lock`, after which every subsequent pull on that repository fails with `cannot lock ref`. The sync pass sweeps transient pull locks before executing and logs each removal.
2. **Unborn clones.** An empty upstream produces a local repository with no commits; `git pull` fails permanently with "no such ref was fetched". The sync pass classifies these as unborn and excludes them, reporting them explicitly — they remain in-sync under $\mathcal{OK}$ in verification.
3. **Storage-layer flapping.** The corpus lives on an external volume that intermittently denies I/O under sustained load. Every pipeline stage emits typed outcomes; the orchestration layer reports per-repository exit codes with captured stderr tails, so a flap-associated failure is visible in the run report rather than silent in a shell pipeline.

Each of these was discovered by a real run, reproduced, fixed behind a test, and is now exercised by the zero-mock suite on every CI run — the failure modes are part of the system's tested surface, not war stories.