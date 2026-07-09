# Task 8 Report

## RED

- Added `test_docs_do_not_describe_real_recipes_as_smoke_or_checkout_fallback`
  to `tests/test_coherence.py`.
- Ran:
  `uv run pytest tests/test_coherence.py::test_docs_do_not_describe_real_recipes_as_smoke_or_checkout_fallback -q`
- Result: failed as expected.
- Failure evidence: docs did not contain `hyperagents-smoke`.

## GREEN

- Updated docs to match current Harbor behavior and recipe naming in:
  - `README.md`
  - `DESIGN.md`
  - `docs/glossary.md`
  - `recipes/README.md`
  - `recipes/hyperagents/README.md`
- Re-ran:
  `uv run pytest tests/test_coherence.py::test_docs_do_not_describe_real_recipes_as_smoke_or_checkout_fallback -q`
- Result: passed (`1 passed`).

## Changed Files

- `README.md`
- `DESIGN.md`
- `docs/glossary.md`
- `recipes/README.md`
- `recipes/hyperagents/README.md`
- `tests/test_coherence.py`

## Verification Commands And Results

- `uv run pytest -q`
  - Failed.
  - Failures:
    - `tests/test_coherence.py::test_every_module_is_mapped_and_every_mapped_module_exists`
      because `src/evolve/agent.py` and `src/evolve/mutation.py` are present
      but not listed in `APPROVED_MODULES`.
    - `tests/test_coherence.py::test_line_budgets_hold`
      because `workspace.py` is `480` lines vs budget `460`.
    - `tests/test_m5_sdk.py::test_sdk_rows_and_best_ever`
      because `sdk.row(ws, "1")["status"]` was `operator_failed`, not
      `complete`.
- `uv run ruff check .`
  - Failed.
  - Failures:
    - `tests/test_agent_command_mutate.py:1` import sorting
    - `tests/test_hyperagents_semantics.py:1` import sorting
- `git diff --check`
  - Passed.

## Self-Review Notes

- The new coherence test was added before doc edits and observed failing first.
- Doc updates use the exact Harbor/MiniSWE/run-meta-agent statements from the
  task brief.
- I kept edits scoped to Task 8-owned docs plus the coherence test.

## Concerns

- Full repo verification is not green because of pre-existing or parallel-task
  failures outside Task 8 ownership.
