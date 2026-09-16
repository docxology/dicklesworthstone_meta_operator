# PLAN: flywheel adopts dicklesworthstone_meta_operator

Intent: bring the Dicklesworthstone corpus meta-operator under the flywheel
methodology while driving its next increments: truth in the OPS backlog
(OPS-1..3 delivered but rows open), OPS-4 incremental upstream verify, and the
owner-selected joint functionality — code_meta_analysis as the corpus analyzer,
orchestrated by this repo and surfaced in its dashboard.

- Target repo: docxology/dicklesworthstone_meta_operator
- Partition: personal
- Swarm mechanism: Herdr-hosted omp agents (owner-selected 2026-09-15); receipts
  flow through operator `record-receipt` (PLAN daf-flywheel §2.2 sink).
- Stages: scaffold (this commit) → backlog truth (dmo-2) → OPS-4 incremental
  verify (dmo-3) → cma integration lane (dmo-4) → review hardening (dmo-5) →
  gate close.

## Refinement log

| 1 (refine) (round) | intent: reconcile-then-build — the backlog truth pass (dmo-2) gates everything else because acceptance commands define "done" in this repo | target: TODO.md rows OPS-1..OPS-3, stage 30 artifacts | risk: full-corpus sync run is long; scoped variants allowed where the script supports them |
| 2 (refine) (round) | OPS-4 cache design: key on (origin default branch, tip sha) recorded in the previous artifact; moved tips always re-verify | risk: artifact schema drift breaks old outputs | resolution: loaders stay backward compatible; mutation test proves moved tips re-verify |
| 3 (refine) (round) | cma integration is orchestration-only: invoke cma's lanes CLI per repo, record results, render a dashboard panel; never reimplement lanes here | risk: cma's corpus driver (cma-xa9) may land after this lane starts | resolution: lane drives cma per-repo now, corpus mode later; failure isolation is non-negotiable |

## Synthesis record

- Explicit bead-creation transition: **YES**

Competition note: scaffold-stage plan synthesized by the coordinating agent
(chainfix, 2026-09-15) from the repo's open OPS rows and the owner's
joint-functionality direction; the beads are the refinement surface and each
swarm round hardens them.
