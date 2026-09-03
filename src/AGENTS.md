# src/ — Agent Guide

Contract first: `models.py`, `jsonio.py`, `config.py`, `project_paths.py` are
frozen — changing them requires updating every importer and the artifact-shape
table in `../docs/architecture.md` in the same change.

## Key concepts

- **Workflow modules never import each other.** They share data through JSON
  artifacts (exact shapes in `../docs/architecture.md`). This is what makes
  each stage re-runnable and each module testable in isolation.
- **State vocabularies are strings with meaning.** `UpstreamStatus.state`,
  `CloneOutcome.status`, `AUTO_COMMAND_KEYS`, `UPSTREAM_OK_STATES` — consumed
  by dashboard chips, gate checks, and reports. Never rename locally.
- **Subprocess boundaries stay thin.** Parsing/decision logic is a pure
  function next to the subprocess wrapper, so tests hit real git fixtures and
  the logic directly.
- **Zero-mock testability**: if new code needs a mock, restructure until it
  needs a real fixture instead (see `../docs/testing_philosophy.md`).

## Adding a module

1. Write the module with full type hints + docstrings.
2. Write `tests/test_<module>.py` with real fixtures (zero-mock).
3. Update `README.md` table + `../AGENTS.md` layer contract.
4. If it introduces a new artifact, add its shape to
   `../docs/architecture.md` and a health-gate check if it gates anything.

## Anti-patterns

- Importing a sibling workflow module (breaks stage independence).
- Swallowing subprocess errors into `None` without a typed outcome.
- Unsorted iteration feeding a serialized artifact (determinism violation).
- Printing from `src/` (logging only).
