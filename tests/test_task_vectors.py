import json
import subprocess
import sys
from pathlib import Path

import pytest

from evolve.evaluation import Outcome
from evolve.evaluation.evidence import TaskVectorError, normalize_task_vector, task_passed, trial_results


def test_normalize_legacy_boolean_vector() -> None:
    assert normalize_task_vector({"task-a": True, "task-b": False}) == {
        "schema_version": 1,
        "tasks": {
            "task-a": {"trials": [{"trial": 0, "status": "benchmark_complete", "reward": 1.0}]},
            "task-b": {"trials": [{"trial": 0, "status": "benchmark_complete", "reward": 0.0}]},
        },
    }


@pytest.mark.parametrize("reward", [float("nan"), float("inf"), float("-inf")])
def test_task_vector_rejects_non_finite_rewards(reward: float) -> None:
    with pytest.raises(TaskVectorError, match="non-finite reward"):
        normalize_task_vector(
            {
                "schema_version": 1,
                "tasks": {"task-a": {"trials": [{"trial": 0, "status": "benchmark_complete", "reward": reward}]}},
            }
        )


def test_versioned_vector_preserves_partial_and_infra_trials() -> None:
    vector = {
        "schema_version": 1,
        "tasks": {
            "task-a": {
                "trials": [
                    {"trial": 0, "status": "benchmark_complete", "reward": 1.0},
                    {
                        "trial": 1,
                        "status": "infrastructure_failed",
                        "reward": None,
                        "owner": "evaluator",
                        "exception_type": "VerifierTimeoutError",
                    },
                ]
            }
        },
    }
    assert normalize_task_vector(vector) == vector
    assert task_passed(vector, "task-a") is None


def test_trial_results_converts_normalized_vector_to_canonical_evidence() -> None:
    vector = {
        "schema_version": 1,
        "tasks": {
            "task-a": {
                "trials": [
                    {
                        "trial": 0,
                        "status": "candidate_invalid",
                        "reward": None,
                        "owner": "candidate",
                        "exception_type": "RuntimeError",
                        "exception_message": "declared dependency missing",
                    }
                ]
            }
        },
    }

    assert trial_results(vector)[0].outcome is Outcome.CANDIDATE_INVALID
    assert trial_results(vector)[0].owner == "candidate"
    assert trial_results(vector)[0].exception_type == "RuntimeError"


def test_trial_results_preserves_repair_attempt_provenance() -> None:
    vector = {
        "schema_version": 1,
        "tasks": {
            "task-a": {
                "trials": [
                    {
                        "trial": 0,
                        "status": "benchmark_complete",
                        "reward": 1.0,
                        "source_attempt": 2,
                        "repaired_from_attempt": 1,
                        "repair_reason": "ConnectionError: reset",
                    }
                ]
            }
        },
    }

    trial = trial_results(vector)[0]
    assert trial.source_attempt == 2
    assert trial.repaired_from_attempt == 1
    assert trial.repair_reason == "ConnectionError: reset"


def test_benchmark_agent_timeout_may_preserve_zero_reward() -> None:
    vector = {
        "schema_version": 1,
        "tasks": {
            "task-a": {
                "trials": [
                    {"trial": 0, "status": "timeout", "reward": 0.0, "owner": "benchmark_agent"},
                ]
            }
        },
    }

    assert normalize_task_vector(vector) == vector
    assert task_passed(vector, "task-a") is False


def test_task_passed_treats_scoreable_verifier_timeout_as_failure() -> None:
    vector = {
        "schema_version": 1,
        "tasks": {
            "task-a": {
                "trials": [
                    {
                        "trial": 0,
                        "status": "timeout",
                        "reward": 0.0,
                        "owner": "benchmark_verifier",
                        "exception_type": "VerifierTimeoutError",
                    }
                ]
            }
        },
    }

    assert task_passed(vector, "task-a") is False


def test_non_benchmark_timeout_cannot_carry_reward() -> None:
    with pytest.raises(TaskVectorError, match="non-score-eligible trial.*null reward"):
        normalize_task_vector(
            {
                "schema_version": 1,
                "tasks": {
                    "task-a": {
                        "trials": [
                            {"trial": 0, "status": "timeout", "reward": 0.0, "owner": "evaluator"},
                        ]
                    }
                },
            }
        )


def test_invalid_task_vector_rejects_duplicate_trial_numbers() -> None:
    with pytest.raises(TaskVectorError, match="duplicate trial 0"):
        normalize_task_vector(
            {
                "schema_version": 1,
                "tasks": {
                    "task-a": {
                        "trials": [
                            {"trial": 0, "status": "benchmark_complete", "reward": 1.0},
                            {"trial": 0, "status": "benchmark_complete", "reward": 0.0},
                        ]
                    }
                },
            }
        )


def test_invalid_task_vector_rejects_non_string_task_ids() -> None:
    with pytest.raises(TaskVectorError, match="invalid task entry: 1"):
        normalize_task_vector(
            {
                "schema_version": 1,
                "tasks": {
                    "task-a": {"trials": []},
                    1: {"trials": []},
                },
            }
        )


def test_invalid_task_vector_rejects_boolean_trial_ids() -> None:
    with pytest.raises(TaskVectorError, match="invalid trial for task-a"):
        normalize_task_vector(
            {
                "schema_version": 1,
                "tasks": {
                    "task-a": {
                        "trials": [
                            {"trial": True, "status": "benchmark_complete", "reward": 1.0},
                        ]
                    }
                },
            }
        )


@pytest.mark.parametrize(
    ("status", "reward", "message"),
    [
        ("benchmark_complete", None, "benchmark_complete trial.*numeric reward"),
        ("cancelled", 0.0, "non-score-eligible trial.*null reward"),
    ],
)
def test_invalid_task_vector_rejects_inconsistent_status_reward(
    status: str, reward: float | None, message: str
) -> None:
    with pytest.raises(TaskVectorError, match=message):
        normalize_task_vector(
            {
                "schema_version": 1,
                "tasks": {
                    "task-a": {
                        "trials": [
                            {"trial": 0, "status": status, "reward": reward},
                        ]
                    }
                },
            }
        )


@pytest.mark.parametrize("status", ["candidate_invalid", "infrastructure_failed"])
def test_structured_failure_may_retain_diagnostic_reward(status: str) -> None:
    vector = {
        "schema_version": 1,
        "tasks": {
            "task-a": {
                "trials": [
                    {
                        "trial": 0,
                        "status": status,
                        "reward": 0.0,
                        "owner": "candidate" if status == "candidate_invalid" else "infrastructure",
                        "exception_type": "RuntimeError",
                    }
                ]
            }
        },
    }

    assert trial_results(vector)[0].reward == 0.0


def test_stub_eval_emits_configured_completed_trials_without_changing_score(tmp_path: Path) -> None:
    evaluator_dir = tmp_path / "evaluator"
    evaluator_dir.mkdir()
    (evaluator_dir / "eval.env").write_text("EVOLVE_HARBOR_ATTEMPTS=3\n")
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "agent.py").write_text("# FAIL task-0\n")
    run_dir = tmp_path / "run"
    script = Path(__file__).resolve().parents[1] / "scaffolds" / "workspace" / "evaluator" / "stub_eval.py"

    result = subprocess.run(
        [sys.executable, str(script), str(run_dir)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2, result.stderr
    assert float((run_dir / "score").read_text()) == 7 / 8
    vector = json.loads((run_dir / "task_vector.json").read_text())
    for task in vector["tasks"].values():
        assert [trial["trial"] for trial in task["trials"]] == [0, 1, 2]
        assert all(trial["status"] == "benchmark_complete" for trial in task["trials"])
    artifacts = json.loads((run_dir / "evaluation_artifacts.json").read_text())
    assert len(artifacts["trials"]) == 8 * 3
    assert all((run_dir / "artifacts" / trial["files"][0]["path"]).is_file() for trial in artifacts["trials"])
