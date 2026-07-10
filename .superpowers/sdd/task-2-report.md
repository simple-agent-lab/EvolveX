# Task 2 report: trusted proposal lifecycle

## Status

Implemented and committed Task 2 on `codex/method-faithful-hyperagents`.

- Commit: `8f83b649f5454c733f4ab847dbeaa990fde5bb46 Make self-modifying proposals atomic`
- Starting point: `317d85d Add candidate validation operator`
- Worktree: `/Users/bytedance/Desktop/simple-evolve-agent/.worktrees/method-faithful-hyperagents`
- Main checkout was not modified.

## Implemented behavior

1. The driver computes the complete candidate diff immediately after `meta_agent` succeeds.
2. No-change and out-of-surface proposals are terminally rejected before any post-proposal operator runs.
3. An optional configured `validate` operator runs against the uncommitted, surface-compliant child.
4. `accept: false` records `rejected_validation`, preserves `validate/result.json`, and creates no `gen/<id>` tag.
5. Self-modification admission now accepts or rejects the complete child atomically. Rejection records `rejected_admission`, writes `meta_eval.json`, and creates no child tag.
6. Both new rejection statuses are terminal and unretryable.
7. Framework feedback generation was retired: the driver no longer creates `runs/gen-N/feedback/`, `feedback.py` was deleted, and the SDK passes `rollout/summary.json` directly as the meta-agent observation.
8. Architecture, design, README, protocol, coherence, and SDK contract tests were migrated. No HyperAgents-specific policy was added to the driver.

## RED evidence

Initial command:

```text
uv run pytest \
  tests/test_m3_meta_eval.py::test_driver_rejects_complete_child_when_self_modification_is_not_admitted \
  tests/test_m5_driver_operators.py::test_validate_rejection_happens_before_candidate_commit -v
```

Observed:

- Atomic admission test failed as intended: old status was `complete`, not `rejected_admission`.
- The first validation run exposed a test-fixture mismatch before reaching driver behavior: generated smoke YAML rendered `meta_agent` without a `variant` field, so the insertion assertion failed. I corrected the fixture to insert before the stable `gate: {}` line and reran RED.

Correct validation RED rerun:

```text
uv run pytest tests/test_m5_driver_operators.py::test_validate_rejection_happens_before_candidate_commit -v
```

Observed expected behavioral failure:

```text
AssertionError: assert 'complete' == 'rejected_validation'
1 failed
```

This proved the old driver ignored the configured validation operator and committed/evaluated the child.

## GREEN evidence

After the minimal lifecycle implementation:

```text
uv run pytest \
  tests/test_m3_meta_eval.py::test_driver_rejects_complete_child_when_self_modification_is_not_admitted \
  tests/test_m5_driver_operators.py::test_validate_rejection_happens_before_candidate_commit -v
```

Result:

```text
2 passed in 1.91s
```

Focused Task 2 contract suite:

```text
uv run pytest tests/test_m3_meta_eval.py tests/test_m5_driver_operators.py \
  tests/test_m2_feedback_candidate_edits.py tests/test_phase_f_interfaces_sdk.py \
  tests/test_coherence.py -v
```

Result: `17 passed, 1 failed`. The sole failure is the explicitly accepted pre-existing public-documentation assertion requiring the literal `hyperagents-smoke`; all Task 2 tests, module-map checks, and line-budget checks passed.

Final focused rerun produced the same evidence: `17 passed, 1 accepted docs failure in 8.74s`.

## Full-suite evidence

```text
uv run pytest -v
```

Result:

```text
61 passed, 1 failed in 73.62s
```

The only failure was:

```text
tests/test_coherence.py::test_docs_do_not_describe_real_recipes_as_smoke_or_checkout_fallback
AssertionError: assert 'hyperagents-smoke' in text
```

This is the accepted Task 7/public-documentation coherence failure identified in the brief. There were no additional failures.

Static verification:

```text
.venv/bin/ruff check src/evolve/driver.py src/evolve/frozen/sdk.py \
  tests/test_m2_feedback_candidate_edits.py tests/test_m3_meta_eval.py \
  tests/test_m5_driver_operators.py tests/test_phase_f_interfaces_sdk.py
git diff --check
```

Result: Ruff reported `All checks passed!`; `git diff --check` produced no output.

## Files committed

- `src/evolve/driver.py`
- `src/evolve/frozen/sdk.py`
- `src/evolve/feedback.py` (deleted)
- `tests/test_m3_meta_eval.py`
- `tests/test_m5_driver_operators.py`
- `tests/test_m2_feedback_candidate_edits.py`
- `tests/test_phase_f_interfaces_sdk.py` (approved direct SDK observation-contract migration)
- `tests/test_coherence.py`
- `ARCHITECTURE.md`
- `DESIGN.md`
- `README.md`
- `library/PROTOCOL.md`

## Self-review

- Confirmed the surface check is after `meta_agent` and before validate, meta-eval, novelty, commit, evaluation, gate, and record.
- Confirmed validation and admission reject the uncommitted child and therefore cannot leave a generation tag or partial child commit.
- Confirmed admission considers the original complete `mutated_paths`; the old operator-only checkout/reversion path and `operator_reverted` bookkeeping are gone.
- Confirmed `_load_validate_payload` and `_operator_output_error("validate", ...)` both use Task 1's `validate_validate_file_payload` contract.
- Confirmed `rejected_validation` and `rejected_admission` are in terminal/unretryable status handling.
- Confirmed framework feedback generation/imports/module-map/docs were removed and rollout summary remains present for observation.
- Confirmed the architecture per-module budget was reallocated from the deleted feedback module while the total mechanism line budget was not increased; coherence budget tests pass.
- Confirmed the staged commit contained exactly the 12 Task 2 files above and no unrelated changes.
- Confirmed no method- or HyperAgents-specific driver policy was introduced.

## Concerns

- Known only: the public docs do not yet contain the literal `hyperagents-smoke`, so the one accepted coherence assertion remains for the later documentation task.
- The focused `uv run` rerun initially hit a sandbox denial reading the user-level uv cache; rerunning with the approved uv permission produced the test result recorded above. This was environmental, not a code failure.

## Task 2 review-fix report: manual commit surface rejection

Changed files:

- `src/evolve/driver.py`
- `tests/test_manual_commit.py`
- `templates/workspace/program.md`
- `templates/workspace/operators/meta_agent_brief.md`

Fix summary:

- Added a regression for manual `evolve fork` + `evolve commit` where a child mutates `README.md`, outside the configured mutable surface.
- Verified the regression failed first because the old code created `gen/1` for an invalid surface proposal.
- Moved manual `commit_child()` surface rejection before `commit_paths()` and `create_tag()`, reusing the generic candidate-rejection archive path.
- Preserved no-proposal behavior: no-change manual commits still return before surface checks and before commit/tag creation.
- Updated workspace template prose to reference `runs/gen-<id>/rollout/summary.json` instead of the retired `runs/gen-<id>/feedback/` directory.

Tests run:

```text
uv run pytest tests/test_manual_commit.py -q
```

Red result before production change:

```text
FAILED tests/test_manual_commit.py::test_manual_commit_rejects_surface_violation_without_child_commit_or_tag
AssertionError: assert 'gen/1' == ''
```

Green/focused results after production change:

```text
uv run pytest tests/test_manual_commit.py -q
1 passed in 1.19s

uv run pytest tests/test_manual_commit.py tests/test_m3_population_self_reference.py tests/test_m0_init.py -q
5 passed in 9.39s

uv run python -m py_compile src/evolve/driver.py
passed

rg -n "feedback/|feedback bundle|runs/gen-<id>/feedback" templates/workspace
no matches
```

Concerns:

- None for this review fix.
