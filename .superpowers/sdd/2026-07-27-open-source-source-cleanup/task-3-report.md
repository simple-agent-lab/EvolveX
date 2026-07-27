# Task 3 report: scaffolds and seeds

## Files changed

- Replaced the mixed `templates/` tree with `scaffolds/workspace/`,
  `scaffolds/evaluators/harbor/`, and `seeds/codex/`.
- Deleted only the obsolete MiniSWE target template, local evaluator engine,
  `novelty.md`, and `trace_analyzer.md`, plus generated cache remnants listed
  below.
- Added named `scaffold_root()` and `seed_root()` resource helpers; workspace
  initialization now selects common scaffolds and evaluator-engine scaffolds
  separately, and copies the Codex seed from `seeds/`.
- Updated packaging, resource-path tests, hygiene roots, the remaining Harbor
  engine test, and the stale frozen-module ownership comment.
- Added `tests/test_resource_layout.py`.

## TDD evidence

- RED: `uv run pytest -q tests/test_resource_layout.py` failed during
  collection because `scaffold_root` and `seed_root` were not importable.
- GREEN: the same test passed after the named roots and resource moves.
- Focused suite: 69 passed:
  `tests/test_resource_layout.py tests/test_m0_init.py tests/test_m7_codex_seed.py
  tests/test_harbor_artifacts.py tests/test_harbor_evaluator_template.py
  tests/test_hyperagents_harbor_recipe.py tests/test_runtime.py
  tests/test_task_vectors.py tests/test_import_hygiene.py`.
- Full suite: `env PYTHONDONTWRITEBYTECODE=1 uv run pytest -q` — 423 passed.

## Build evidence

- `uv build` succeeded.
- The final wheel listing contains `evolve/scaffolds/`, `evolve/seeds/codex/`,
  and `evolve/recipes/`; it contains no `evolve/templates/` entry.

## Self-review

- `git diff --check` passed.
- `templates/` is absent; no cache files remain under `scaffolds/` or `seeds/`.
- Old resource-root scan found only the intentional absence assertions in
  `tests/test_resource_layout.py`.
- The remaining `builtin-dummy` matches in `src/evolve/workspace.py` are the
  inherited Task 1 test-only rejection guards, covered by `tests/test_m0_init.py`;
  they do not load a test resource or expose a production seed.

## Cache-removal exception

`apply_patch` cannot decode binary `.pyc` files. With coordinator approval, the
following generated files were removed with explicit `unlink`, followed only by
verified-empty `rmdir` calls:

- `templates/evaluator/__pycache__/harbor_artifacts.cpython-314.pyc`
- `templates/target/harbor/__pycache__/miniswe_source_agent.cpython-314.pyc`
- `templates/workspace/evolve_harbor_adapter/__pycache__/__init__.cpython-314.pyc`
- `templates/workspace/evolve_harbor_agent/__pycache__/__init__.cpython-314.pyc`
- `scaffolds/evaluators/harbor/__pycache__/harbor_artifacts.cpython-314.pyc`

## Concerns

None.
