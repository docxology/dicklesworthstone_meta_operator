# docs/ — Agent Guide

Hub-and-spoke: this directory holds the rules; the code holds the truth. When
documentation and code disagree, fix whichever is wrong — and keep the artifact
shape table in [`architecture.md`](architecture.md) in the same commit as any
producer/consumer change (the health gate and tests enforce the shapes).

## Rules

- No session logs, "fixed this session" narration, or round-numbered process
  logs. The docs read as one present-state story.
- Every claimed behavior links to a file, symbol, or acceptance command — no
  vague "validated with standard approaches".
- Counts (test totals, coverage %, repo counts) are generated data; do not
  hardcode them in prose. Link the artifact or gate that reports them.
