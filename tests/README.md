# tests/ — Zero-Mock Test Suite

Real git fixture repos, real subprocesses, real files — offline. No
`unittest.mock`/`MagicMock`/`@patch`/`create_autospec`. `pytest.MonkeyPatch`
only on module attributes for error paths. See
`../docs/testing_philosophy.md`.

| File | Covers |
| --- | --- |
| `test_contract.py` | models round-trips + vocabularies, jsonio atomicity, config typing/validation, project_paths |
| `test_github_client.py` | `parse_repos`, pagination shapes, PATH-stubbed `gh` subprocess |
| `test_registry.py` | registry build/save/load round-trip, name/metadata accessors |
| `test_cloner.py` | plan/execute against real bare fixture repos, idempotence, failure capture |
| `test_upstream_check.py` | all nine states via real git operations, prev-tips cache round-trip |
| `test_git_probe.py` | explicit-checkout probe binding, timeout outcomes, ancestor isolation |
| `test_inventory.py` | language counting, manifests, entry points, auto-cmds, README digests |
| `test_orchestrator.py` | selectors, run execution, timeouts, tails, reports |
| `test_dashboard.py` | payload load, summary math, deterministic HTML/catalog render, XSS escaping |
| `test_cma_lane.py` | cma lane composition against a real fake `lanes.py` checkout |
| `test_figures.py` | real matplotlib PNGs, byte-level determinism |
| `test_manuscript_variables.py` | `{{TOKEN}}` map ↔ manuscript prose, both directions |
| `test_source_evidence.py` | gate snapshots, input manifests, receipt checks |
| `test_health_gate.py` | every check pass/fail branch against real artifact trees |
| `test_scripts_smoke.py` | preflight `--offline` subprocess run + `--help`/compile checks |

Canonical gate (from the project directory):

```bash
uv run pytest tests/ --cov=src --cov-fail-under=90 -q
```

From the monorepo root (CI parity):

```bash
uv run pytest projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/tests/ \
  --cov=projects/ongoing/Code_Tools/dicklesworthstone_meta_operator/src --cov-fail-under=90
```

`conftest.py` inserts project root + `src/` on `sys.path`.
