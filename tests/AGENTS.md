# tests/ — Agent Guide

## Before writing any test

Read `../docs/testing_philosophy.md`. Hard rules:

1. Zero mocks. Real git fixtures (`git init --bare` in `tmp_path` + real
   clones), real subprocesses, real files. If you need a fake, restructure the
   code under test until a real fixture suffices.
2. Offline. No github.com. Local-path remotes are the fixture pattern for all
   git interactions.
3. `pytest.MonkeyPatch` on module attributes only for error-path injection.
4. Assert observable behavior: exit codes, state strings, artifact shapes,
   rendered content. Not call counts.
5. Every test file runs in isolation (`pytest tests/test_X.py`) and in the
   full suite; no shared mutable state between tests; use `tmp_path`.

## Fixture patterns

- **Upstream repo**: `git init --bare` a dir, `git init -b main` a seed dir,
  commit, `git push` — then `git clone <bare> work`. Manipulate `work`
  (commit / dirty file / `checkout --detach` / `checkout -b`) and assert
  `upstream_check.verify_one` states.
- **gh CLI**: write an executable shell script that prints a fixture JSON
  page, prepend its dir to `PATH` via `monkeypatch.setenv`, then call
  `enumerate_repos` — the real subprocess path runs.
- **Artifacts**: build the exact JSON shapes from `../docs/architecture.md`
  with `src.jsonio.write_json` in a `tmp_path` project tree, then run gates
  and renderers against it.

## Coverage

`pyproject.toml` gates ≥90 % branch coverage on `src/`. Do not delete tests
or add exclusions to make the number — add behavioral tests for the gap.
