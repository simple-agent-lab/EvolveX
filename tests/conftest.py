import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from evolve.archive import merged_rows as mechanism_merged_rows

# These production-faithful scenarios are useful for explicit audits, but they
# repeat subprocess and Git-worktree paths already represented in the default
# suite. Keep exact node IDs here so collection fails if this boundary drifts.
_EXTENDED_TESTS = frozenset(
    {
        "tests/test_candidate_smoke.py::test_candidate_smoke_cli_requires_full_and_prints_bounded_stderr_tail",
        "tests/test_candidate_smoke.py::test_smoke_attempts_are_append_only_generic_records",
        "tests/test_evaluation_lifecycle.py::test_cancelled_attempt_is_recorded_and_never_retried",
        "tests/test_evaluation_lifecycle.py::test_cleanup_cancellation_is_recorded_under_allocated_attempt",
        "tests/test_evaluation_lifecycle.py::test_failed_real_genesis_is_not_selectable",
        "tests/test_evaluation_lifecycle.py::test_genesis_infrastructure_retries_same_commit_once",
        "tests/test_evaluation_lifecycle.py::test_genesis_retry_terminal_is_canonical_and_persistent",
        "tests/test_evaluation_lifecycle.py::test_later_retry_terminal_is_canonical_and_does_not_resume",
        "tests/test_evaluation_lifecycle.py::test_later_terminal_candidate_does_not_retry_or_run_gate",
        "tests/test_evaluation_lifecycle.py::test_malformed_second_attempt_is_recorded_and_restart_never_allocates_third",
        "tests/test_evaluation_lifecycle.py::test_two_genesis_infrastructure_failures_pause_before_evolution",
        "tests/test_evaluation_lifecycle.py::test_two_later_infrastructure_failures_pause_without_advancing",
        "tests/test_harbor_evaluator_template.py::test_harbor_jobs_are_owned_by_run_and_existing_jobs_fail_without_deletion",
        "tests/test_harbor_evaluator_template.py::test_harbor_registry_dataset_uses_dataset_flag_and_task_file",
        "tests/test_m8_dataset_splits.py::test_harbor_evaluator_shell_routes_gate_and_sealed_tasks",
        "tests/test_harbor_evaluator_template.py::test_nonzero_harbor_exit_overrides_reward_and_preserves_cost",
        "tests/test_hyperagents_semantics.py::test_hyperagents_forbidden_operator_edit_rejects_entire_child",
        "tests/test_m1_evaluator_invariants.py::test_candidate_wide_structured_setup_failure_beats_nonzero_exit",
        "tests/test_m1_evaluator_invariants.py::test_canonical_infrastructure_failure_retries_and_success_replaces_it",
        "tests/test_m1_evaluator_invariants.py::test_canonical_terminal_outcomes_are_not_reevaluated_on_resume",
        "tests/test_m1_evaluator_invariants.py::test_evaluate_uses_exact_commit_attempt_and_ignores_compatibility_score",
        "tests/test_m1_evaluator_invariants.py::test_evaluator_path_commit_is_invalid_and_eval_does_not_stamp_score",
        "tests/test_m1_evaluator_invariants.py::test_eval_force_re_evaluates_completed_generation_zero",
        "tests/test_m1_evaluator_invariants.py::test_force_re_evaluation_appends_complete_record_evidence",
        "tests/test_m1_evaluator_invariants.py::test_infrastructure_failed_eval_is_scoreless_invalid_parent",
        "tests/test_m1_evaluator_invariants.py::test_mechanism_eval_can_replace_initial_scaffold_score",
        "tests/test_m1_evaluator_invariants.py::test_ordinary_evaluation_is_marked_and_receipted",
        "tests/test_m1_evaluator_invariants.py::test_reward_bearing_candidate_failure_is_classified_after_ingestion",
        "tests/test_m1_evaluator_invariants.py::test_timeout_zero_scoring_requires_literal_true",
        "tests/test_m0_run_resume.py::test_resume_continues_from_last_complete_generation_without_duplicates",
        "tests/test_m2_feedback_candidate_edits.py::test_no_framework_feedback_bundle_is_created",
        "tests/test_m3_population_self_reference.py::test_out_of_surface_operator_edit_is_caught_and_recorded",
        "tests/test_m3_population_self_reference.py::test_population_fanout_creates_branching_lineage",
        "tests/test_m4_presets_bootstrap.py::test_status_and_report_recompute_best_from_stamped_scores",
        "tests/test_m5_driver_operators.py::test_driver_does_not_inject_verified_fixes_for_other_record_operators",
        "tests/test_m5_driver_operators.py::test_driver_has_no_package_manager_specific_admission",
        "tests/test_m5_driver_operators.py::test_jsonl_record_computes_verified_fixes_from_task_vectors",
        "tests/test_m5_driver_operators.py::test_run_records_operator_failed_when_meta_agent_operator_crashes",
        "tests/test_m5_driver_operators.py::test_run_uses_operator_subprocesses_for_loop_steps",
        "tests/test_m5_driver_operators.py::test_validate_rejection_happens_before_candidate_commit",
        "tests/test_m5_record_verb.py::test_gate_certification_resists_malicious_record[reject-parents1]",
        "tests/test_m5_record_verb.py::test_gate_operator_failure_runs_terminal_record_once_and_preserves_failure",
        "tests/test_m5_record_verb.py::test_gate_verdict_survives_record_failure",
        "tests/test_m5_record_verb.py::test_record_failure_preserves_validation_rejection_status",
        "tests/test_m5_record_verb.py::test_run_records_rejected_no_proposal_attempt",
        "tests/test_m5_record_verb.py::test_select_operator_failure_runs_terminal_record_once_and_preserves_failure",
        "tests/test_m5_record_verb.py::test_successful_terminal_record_is_idempotent",
        "tests/test_m5_record_verb.py::test_terminal_record_cannot_overwrite_primary_outcome_fields",
        "tests/test_m5_sdk.py::test_sdk_rows_and_best_ever",
        "tests/test_m6_per_round_sampling.py::test_static_sampling_can_select_generation_one_for_generation_two",
        "tests/test_m7_verify.py::test_verify_passes_clean_ledger_and_flags_tampering",
        "tests/test_m8_dataset_splits.py::test_final_sealed_anchor_is_auxiliary_and_absent_from_mutator_lineage",
        "tests/test_manual_commit.py::test_manual_commit_has_no_package_manager_specific_admission",
        "tests/test_manual_commit.py::test_manual_commit_rejects_surface_violation_without_child_commit_or_tag",
        "tests/test_phase_f_seam_validation.py::test_malformed_select_output_records_operator_failed_with_file_and_field",
        "tests/test_runtime.py::test_evaluator_runs_through_owned_process_helper",
    }
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    matched: set[str] = set()
    for item in items:
        base_nodeid = item.nodeid.split("[", 1)[0]
        configured_nodeid = item.nodeid if item.nodeid in _EXTENDED_TESTS else base_nodeid
        if configured_nodeid in _EXTENDED_TESTS:
            item.add_marker(pytest.mark.extended)
            matched.add(configured_nodeid)

    missing = sorted(_EXTENDED_TESTS - matched)
    if config.args == ["tests"] and missing:
        raise pytest.UsageError("stale extended test node IDs: " + ", ".join(missing))


@pytest.fixture(autouse=True)
def evaluator_runtime_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVOLVE_RUNTIME_DIGEST", "sha256:test-runtime")
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "evolve-home"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def run_evolve(
    *args: str,
    env: dict[str, str | None] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        for key, value in env.items():
            if value is None:
                merged_env.pop(key, None)
            else:
                merged_env[key] = value
    if env and env.get("EVAL_STUB") == "1" and "EVOLVE_AGENT_COMMAND" not in env:
        merged_env["EVOLVE_AGENT_COMMAND"] = smoke_agent_command()
    return subprocess.run(
        [sys.executable, "-m", "evolve", *args],
        text=True,
        capture_output=True,
        env=merged_env,
        cwd=cwd,
        check=False,
    )


def smoke_agent_command() -> str:
    code = (
        "import os\n"
        "from pathlib import Path\n"
        "target = Path('target/agent.py')\n"
        "genid = os.environ.get('EVOLVE_GENID', 'unknown')\n"
        "target.write_text(target.read_text() + f'\\n# smoke-meta-agent gen {genid}\\n')\n"
        "print('predicted_fixes: []')\n"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


def smoke_env(evolve_home: Path) -> dict[str, str]:
    return {
        "EVAL_STUB": "1",
        "EVOLVE_HOME": str(evolve_home),
        "EVOLVE_AGENT_COMMAND": smoke_agent_command(),
    }


def write_locked_miniswe_seed(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'mini-swe-agent'\n"
        "version = '0.0.0'\n"
        "requires-python = '>=3.11'\n"
        "dependencies = []\n"
    )
    package = path / "src" / "minisweagent"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("__version__ = '0.0.0'\n")
    result = subprocess.run(
        ["uv", "lock", "--offline", "--python", sys.executable, "--project", str(path)],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", "/tmp/simple-evolve-agent-test-uv")},
    )
    assert result.returncode == 0, result.stderr
    return path


def git(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(workspace), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def init_workspace(tmp_path: Path, experiment: str = "experiment") -> tuple[Path, Path]:
    workspace = tmp_path / experiment
    evolve_home = tmp_path / "evolve-home"
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hill_climb-smoke",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert result.returncode == 0, result.stderr
    return workspace, evolve_home


def init_miniswe_workspace(tmp_path: Path, experiment: str = "miniswe-experiment") -> tuple[Path, Path]:
    workspace = tmp_path / experiment
    evolve_home = tmp_path / "evolve-home"
    seed = write_locked_miniswe_seed(tmp_path / "miniswe-seed")
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hill_climb",
        "--seed",
        str(seed),
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert result.returncode == 0, result.stderr
    return workspace, evolve_home


def rows_by_genid(workspace: Path) -> dict[str, dict[str, object]]:
    return {str(row["genid"]): row for row in mechanism_merged_rows(workspace / "archive.jsonl")}


def git_show(workspace: Path, spec: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(workspace), "show", spec],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    return result.stdout


def append_archive_event(workspace: Path, evolve_home: Path, event: dict[str, object]) -> None:
    line = json.dumps(event, sort_keys=True) + "\n"
    with (workspace / "archive.jsonl").open("a") as archive:
        archive.write(line)
    mirror = evolve_home / "mirrors" / workspace.name / "archive.jsonl"
    with mirror.open("a") as archive:
        archive.write(line)
