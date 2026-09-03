# Testing Philosophy: The Zero-Mock Standard

Inherited from the template (`templates/template_code_project/docs/testing_philosophy.md`):
if a function requires a mock to be tested, it is doing I/O — which belongs
behind a tested boundary, not hidden behind a fake.

## How this project applies it

| Concern | Test technique |
| --- | --- |
| Git clone/verify/branch states | REAL git: `git init --bare` fixture remotes in `tmp_path`, real clones, real commits/pushes/fetches/detaches. Offline (local-path remotes). |
| GitHub enumeration | Pure `parse_repos` on realistic fixture dicts; the subprocess path is exercised through a REAL executable — a `gh` shell-script stub placed on `PATH` that emits fixture pages. |
| Inventory | REAL files in `tmp_path` (multi-language trees, manifests, oversized files, binary-safe reads). |
| Orchestration | REAL subprocess runs (`python3 -c …`), real timeouts, real tail truncation. |
| Dashboard/gate | REAL artifact trees in `tmp_path`; renderers asserted pure + deterministic + XSS-escaping. |
| Artifact I/O | Real atomic-write behavior: crash-safety via `os.replace`, strict required-reads. |

## Hard rules

1. No `unittest.mock`, `MagicMock`, `@patch`, `create_autospec`, or mock factories anywhere in `tests/`.
2. `pytest.MonkeyPatch` only on module attributes for error-path injection (e.g. forcing a helper to raise); never to fake a return value of the function under test.
3. Tests are offline; no github.com dependency. `gh auth`-dependent behavior is a script concern (00_preflight), not a test dependency.
4. Assertions verify observable behavior (exit codes, state strings, artifact shapes, HTML content), not call counts.
5. Coverage gate: ≥90 % branch coverage on `src/` (`pyproject.toml`, `fail_under = 90`, `branch = true`).

## Running the gate

```bash
cd projects/ongoing/Code_Tools/dicklesworthstone_meta_operator
uv run pytest tests/ --cov=src --cov-fail-under=90 -q
```

A green exit code alone is not proof the suite ran: confirm tests collected
> 0 and coverage ≥ 90 % in the output.
