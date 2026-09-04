# Scope, Related Work, and Positioning {#sec:scope}

## Scope {#sec:scope-limits}

The operator is scoped to a single GitHub user's public corpus under a mirror discipline: local clones are working trees for verification and orchestration, never publication targets, and synchronization is fast-forward-only so no local state can diverge silently. The captured corpus holds {{CORPUS_REPO_TOTAL}} repositories; scale beyond a few thousand repositories would move the bottleneck from process orchestration to storage and rate budgets, which the current design does not claim to address.

Three boundaries are deliberate. First, the operator does not modify third-party code: orchestration runs commands *in* repositories but the fleet remains a mirror. Second, verification compares a clone against its upstream default branch only; branch-level archaeology is out of scope. Third, the GitHub boundary is deliberately thin (`gh api` pagination plus parsing) — the operator's claims are about local state, not about crawling GitHub.

## Relation to existing tooling {#sec:related}

Git's own primitives supply the substrate: the clone-and-verify model assumes a distributed version-control system whose local state is fully inspectable [@chacon2014progit], and every verification query in [@eq:state_machine] is a composition of plumbing commands. The GitHub REST API provides the enumeration that seeds the registry [@github2026restapi]; long-term archival of the corpus's history is the province of Software Heritage [@oracle2026swh], whose vault model complements rather than overlaps the live-mirror discipline.

Fleet managers and infrastructure-as-code systems (Nix, Terraform) provision *environments*; dotfile managers synchronize *configuration*; repository aggregators (code search platforms) index *content*. None couples enumeration to per-clone upstream verification with typed outcomes and a binary gate — the specific loop this system closes. Within the docxology ecosystem, the operator is the first code-tools fork of the research template's *methodology* rather than its scientific content: the layer contract, zero-mock doctrine, thin-orchestrator boundary, and token-gated manuscript are the template's transferable lessons applied to an operations domain [@docxology2026template].

## Positioning {#sec:positioning}

The system is offered as a pattern: enumerate → clone → verify → orchestrate → interpret → render → gate, with every numeric claim artifact-backed. The corpus is incidental; pointing `data/operator_config.yaml` at any GitHub user re-targets the entire pipeline, and the manuscript regenerates from the new evidence.