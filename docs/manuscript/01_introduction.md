# Introduction {#sec:introduction}

A prolific GitHub account accrues repositories faster than any manual workflow can track them. The [Dicklesworthstone corpus](https://github.com/Dicklesworthstone) [@dicklesworthstone2026corpus] holds {{CORPUS_REPO_TOTAL}} public repositories — {{CORPUS_FORK_TOTAL}} of them forks of third-party projects — spanning {{CORPUS_LANG_COUNT}} primary languages and roughly {{CORPUS_TOTAL_SIZE_GB}} GB of packed content. Operating over such a corpus raises three recurring questions that ad-hoc tooling answers badly: which repositories exist right now, which local clones are current with their upstreams, and what is actually *in* each repository — its languages, entry points, test setup, and activity.

Existing tools solve fragments of this. Git mirroring solutions (`git clone --mirror`) preserve refs but provide no working trees to operate in; repository aggregators index code but do not verify local sync state; fleet managers provision environments but rarely couple enumeration to per-clone verification with typed outcomes. The gap this work fills is the **closed loop**: enumerate → clone → verify → orchestrate → interpret → render → gate, with every stage idempotent, re-runnable, and emitting typed artifacts that downstream stages consume.

## Design principles {#sec:principles}

Four principles, all enforced by the template paradigm this project forks [@docxology2026template]:

1. **Thin orchestrators.** `scripts/` parses arguments and delegates; every classification decision lives in `src/` behind a test.
2. **Zero-mock verification.** If a function needs a mock to be tested, it is doing I/O and belongs behind a real boundary. Git behavior is tested against real fixture repositories built by `git init`/`commit` in temporary directories; the GitHub boundary is exercised through a real PATH-stubbed `gh` executable.
3. **Typed outcomes over silent failures.** Every subprocess failure becomes a typed result (`CloneOutcome.status`, `RunResult.timed_out`, `GateCheck.passed=False`) — never swallowed.
4. **Reproducibility by construction.** Every numeric in the manuscript prose is a placeholder token emitted by one generator from tracked artifacts; drift in either direction fails CI ([@sec:reproducibility]).

The system's **primary metric** is the upstream sync ratio, defined in [@eq:sync_ratio]:

$$
\operatorname{sync} \;=\; \frac{\left|\{\, r \in R \;:\; \operatorname{state}(r) \in \mathcal{OK} \}\right|}{N}
$$ {#eq:sync_ratio}

where $N$ is the corpus size, $\operatorname{state}$ is the classification of [@sec:verification-formalism], and $\mathcal{OK} = \{\texttt{on\_upstream}, \texttt{unborn}\}$. At capture time the ratio was {{VERIFY_OK_PCT}} % ({{VERIFY_OK}} of {{VERIFY_TOTAL}}).