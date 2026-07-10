# Task 6 Report: AHE Attribution and Sequential Selection

## Scope

Implemented only the Task 6 library policy surface:

- `library/ahe_support.py`: conservative k-trial task states, deterministic state comparisons, per-change manifest attribution, deterministic debugger task/control selection, manifest validation, and workspace-relative hash verification.
- `library/select/ahe_latest.py`: a dedicated sequential selector that chooses exactly one newest valid parent.
- `tests/test_ahe_support.py`: table-driven policy and manifest validation coverage.
- `tests/test_phase_f_init_binding.py`: confirms the selector is available for workspace library vendoring.

No frozen driver or evaluator mechanism files were modified. No DevBoxS experiments were touched.

## TDD

The first attempted test import used the asset directory as a package and failed with `ModuleNotFoundError: No module named 'library'`. This was a test-harness issue: `library/` is intentionally vendored as operator assets rather than installed as a package. The test was corrected to load the asset by file path. The intended RED command then failed because `library/ahe_support.py` did not exist.

### RED command

```text
$ uv run pytest tests/test_ahe_support.py -v
============================= test session starts ==============================
platform darwin -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0 -- /Users/bytedance/Desktop/simple-evolve-agent/.worktrees/method-faithful-ahe/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/bytedance/Desktop/simple-evolve-agent/.worktrees/method-faithful-ahe
configfile: pyproject.toml
collecting ... collected 0 items / 1 error

==================================== ERRORS ====================================
__________________ ERROR collecting tests/test_ahe_support.py __________________
tests/test_ahe_support.py:11: in <module>
    SPEC.loader.exec_module(AHE_SUPPORT)
<frozen importlib._bootstrap_external>:755: in exec_module
    ???
<frozen importlib._bootstrap_external>:892: in get_code
    ???
<frozen importlib._bootstrap_external>:950: in get_data
    ???
E   FileNotFoundError: [Errno 2] No such file or directory: '/Users/bytedance/Desktop/simple-evolve-agent/.worktrees/method-faithful-ahe/library/ahe_support.py'
=========================== short test summary info ============================
ERROR tests/test_ahe_support.py - FileNotFoundError: [Errno 2] No such file o...
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.06s ===============================
```

### GREEN command

```text
$ uv run pytest tests/test_ahe_support.py -v
============================= test session starts ==============================
platform darwin -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0 -- /Users/bytedance/Desktop/simple-evolve-agent/.worktrees/method-faithful-ahe/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/bytedance/Desktop/simple-evolve-agent/.worktrees/method-faithful-ahe
configfile: pyproject.toml
collecting ... collected 12 items

tests/test_ahe_support.py::test_task_states_require_two_complete_trials PASSED [  8%]
tests/test_ahe_support.py::test_compare_states_orders_improvements_and_regressions PASSED [ 16%]
tests/test_ahe_support.py::test_manifest_attribution_marks_harmful_change PASSED [ 25%]
tests/test_ahe_support.py::test_select_debugger_tasks_uses_seeded_sorted_success_controls PASSED [ 33%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_invalid_evidence_and_coverage[<lambda>-risk_tasks] PASSED [ 41%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_invalid_evidence_and_coverage[<lambda>-failure_evidence] PASSED [ 50%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_invalid_evidence_and_coverage[<lambda>-unsafe path] PASSED [ 58%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_invalid_evidence_and_coverage[<lambda>-changed paths] PASSED [ 66%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_invalid_evidence_and_coverage[<lambda>-exactly once] PASSED [ 75%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_missing_evidence_file PASSED [ 83%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_surface_mismatch PASSED [ 91%]
tests/test_ahe_support.py::test_verify_relative_hash_requires_workspace_relative_matching_file PASSED [100%]

============================== 12 passed in 0.05s ==============================
```

## Final Verification

Required command:

```text
$ uv run pytest tests/test_ahe_support.py tests/test_phase_f_init_binding.py -v
============================== 17 passed in 0.46s ==============================
```

Directly adjacent checks:

```text
$ uv run pytest tests/test_task_vectors.py tests/test_patching.py -v
============================== 13 passed in 1.07s ==============================
```

Final formatted verification:

```text
$ uv run pytest tests/test_ahe_support.py tests/test_phase_f_init_binding.py tests/test_task_vectors.py tests/test_patching.py -v
============================== 30 passed in 1.41s ==============================
```

`uv run ruff check library/ahe_support.py library/select/ahe_latest.py tests/test_ahe_support.py tests/test_phase_f_init_binding.py` passed. `uv run ruff format` reformatted the three applicable files. `git diff --check` passed after formatting.

## Review

- Manifest validation requires explicit risk tasks, nonempty evidence that stays under `run_dir`, safe relative paths, and exact one-to-one changed-path coverage.
- The surface report must be successful and report precisely the same changed paths.
- Hash references must be safe workspace-relative files with a matching SHA-256.
- AHE parent selection is independent of score and uses only the newest valid archive row, breaking ties deterministically by generation id.

## Commit

`19627e4 Add AHE attribution and sequential selection`

The commit contains the four Task 6 implementation/test files. This report is intentionally kept as the requested SDD artifact and is not included in that code commit.

## Review Fix: Sequential Selector Behavior

The review correctly identified that palette availability did not execute
`AheLatestSelect.pick`. Added direct behavioral coverage using a minimal fake
archive. The correct tests passed against commit `19627e4`, so this fix is
test-only. To prove the tests detect a regression, the selector was temporarily
changed to lexical full-genid ordering, the RED run was captured, and the
original numeric-generation plus full-genid tie-break was restored. The mutation
was not committed and `library/select/ahe_latest.py` has no diff.

### Mutation RED

```text
$ uv run pytest tests/test_ahe_select.py -v
============================= test session starts ==============================
platform darwin -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0 -- /Users/bytedance/Desktop/simple-evolve-agent/.worktrees/method-faithful-ahe/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/bytedance/Desktop/simple-evolve-agent/.worktrees/method-faithful-ahe
configfile: pyproject.toml
collecting ... collected 3 items

tests/test_ahe_select.py::test_pick_returns_exactly_newest_numeric_generation FAILED [ 33%]
tests/test_ahe_select.py::test_pick_breaks_numeric_generation_tie_by_full_genid PASSED [ 66%]
tests/test_ahe_select.py::test_pick_exits_when_no_valid_ahe_parent_exists PASSED [100%]

=================================== FAILURES ===================================
_____________ test_pick_returns_exactly_newest_numeric_generation ______________

    def test_pick_returns_exactly_newest_numeric_generation() -> None:
        result = AHE_LATEST.AheLatestSelect().pick(
            FakeArchive([{"genid": "9"}, {"genid": "10"}, {"genid": "2"}]),
            None,
        )

>       assert result.parents == ["10"]
E       AssertionError: assert ['9'] == ['10']
E
E         At index 0 diff: '9' != '10'
E
E         Full diff:
E           [
E         -     '10',
E         ?      ^^...
E
E         ...Full output truncated (3 lines hidden), use '-vv' to show

tests/test_ahe_select.py:27: AssertionError
=========================== short test summary info ============================
FAILED tests/test_ahe_select.py::test_pick_returns_exactly_newest_numeric_generation
========================= 1 failed, 2 passed in 0.04s ==========================
```

### Restored GREEN

```text
$ uv run pytest tests/test_ahe_select.py tests/test_ahe_support.py tests/test_phase_f_init_binding.py -v
============================= test session starts ==============================
platform darwin -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0 -- /Users/bytedance/Desktop/simple-evolve-agent/.worktrees/method-faithful-ahe/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/bytedance/Desktop/simple-evolve-agent/.worktrees/method-faithful-ahe
configfile: pyproject.toml
collecting ... collected 20 items

tests/test_ahe_select.py::test_pick_returns_exactly_newest_numeric_generation PASSED [  5%]
tests/test_ahe_select.py::test_pick_breaks_numeric_generation_tie_by_full_genid PASSED [ 10%]
tests/test_ahe_select.py::test_pick_exits_when_no_valid_ahe_parent_exists PASSED [ 15%]
tests/test_ahe_support.py::test_task_states_require_two_complete_trials PASSED [ 20%]
tests/test_ahe_support.py::test_compare_states_orders_improvements_and_regressions PASSED [ 25%]
tests/test_ahe_support.py::test_manifest_attribution_marks_harmful_change PASSED [ 30%]
tests/test_ahe_support.py::test_select_debugger_tasks_uses_seeded_sorted_success_controls PASSED [ 35%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_invalid_evidence_and_coverage[<lambda>-risk_tasks] PASSED [ 40%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_invalid_evidence_and_coverage[<lambda>-failure_evidence] PASSED [ 45%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_invalid_evidence_and_coverage[<lambda>-unsafe path] PASSED [ 50%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_invalid_evidence_and_coverage[<lambda>-changed paths] PASSED [ 55%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_invalid_evidence_and_coverage[<lambda>-exactly once] PASSED [ 60%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_missing_evidence_file PASSED [ 65%]
tests/test_ahe_support.py::test_validate_change_manifest_rejects_surface_mismatch PASSED [ 70%]
tests/test_ahe_support.py::test_verify_relative_hash_requires_workspace_relative_matching_file PASSED [ 75%]
tests/test_phase_f_init_binding.py::test_init_binds_dgm_select_to_score_weighted_library_variant_and_stamps_protocol PASSED [ 80%]
tests/test_phase_f_init_binding.py::test_ahe_latest_selector_is_available_as_a_library_variant PASSED [ 85%]
tests/test_phase_f_init_binding.py::test_real_recipe_binds_meta_agent_to_agent_command_library_variant PASSED [ 90%]
tests/test_phase_f_init_binding.py::test_operator_assets_vendor_nested_prompt_files PASSED [ 95%]
tests/test_phase_f_init_binding.py::test_recipe_evaluator_assets_copy_training_but_not_sealed_files PASSED [100%]

============================== 20 passed in 0.68s ==============================
```

### Changed Files

- `tests/test_ahe_select.py`
- `.superpowers/sdd/task-6-report.md`

No production behavior changed.
