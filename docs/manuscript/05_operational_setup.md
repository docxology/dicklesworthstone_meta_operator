# Operational Setup {#sec:operational_setup}

This section records the operational configuration under which the captured results were produced, and the infrastructure failure modes encountered while operating a ~{{CORPUS_TOTAL_SIZE_GB}} GB fleet on external storage — both are part of the system's evidence, not its appendix.

## Configuration surface {#sec:config-surface}

The operator's single runtime input is `data/operator_config.yaml`: the target user, clone directory, worker counts, per-run timeout, and captured stream tail size. The saved registry records {{CONFIG_GITHUB_USER}} as the corpus owner and `include_forks: true` at capture time; the manuscript's metadata lives in `docs/manuscript/config.yaml`. Configuration loading is strict: unknown keys are a hard error, because a typo silently ignored is a generator failure masked.

## Unattended steady state {#sec:steady-state}

The full refresh chain — sync, verify, inventory, figures, dashboard, gate — ran as a daily scheduled job on the operator's host during corpus capture. The job waited for storage availability, re-synchronized the canonical tracked tree into the execution tree before running, retried each stage with backoff, mirrored fresh artifacts into the release clone, and published them when tracked artifacts changed. Failures surfaced through the run state. The publication target was the operator's release clone.

## Real infrastructure failure modes {#sec:failure-modes}

Operating a {{CORPUS_REPO_TOTAL}}-repository fleet on consumer hardware surfaced three failure modes that now have typed remediations:

1. **Stale lock files.** A `git pull` killed mid-run leaves `ORIG_HEAD.lock`, after which every subsequent pull on that repository fails with `cannot lock ref`. The sync pass sweeps transient pull locks before executing and logs each removal.
2. **Unborn clones.** An empty upstream produces a local repository with no commits; `git pull` fails permanently with "no such ref was fetched". The sync pass classifies these as unborn and excludes them, reporting them explicitly — they remain in-sync under $\mathcal{OK}$ in verification.
3. **Storage-layer flapping.** The corpus lives on an external volume that intermittently denies I/O under sustained load. Every pipeline stage emits typed outcomes; the orchestration layer reports per-repository exit codes with captured stderr tails, so a flap-associated failure is visible in the run report rather than silent in a shell pipeline.

Repository history records the stale-lock and unborn-clone fixes. The zero-mock suite exercises local Git states and typed failure reporting. The storage incident comes from the operator's run notes and does not establish a test of the external volume.
