import pytest

from evolve.task_vectors import TaskVectorError, normalize_task_vector, task_passed


def test_normalize_legacy_boolean_vector() -> None:
    assert normalize_task_vector({"task-a": True, "task-b": False}) == {
        "schema_version": 1,
        "tasks": {
            "task-a": {"trials": [{"trial": 0, "status": "complete", "reward": 1.0}]},
            "task-b": {"trials": [{"trial": 0, "status": "complete", "reward": 0.0}]},
        },
    }


def test_versioned_vector_preserves_partial_and_infra_trials() -> None:
    vector = {
        "schema_version": 1,
        "tasks": {
            "task-a": {
                "trials": [
                    {"trial": 0, "status": "complete", "reward": 1.0},
                    {
                        "trial": 1,
                        "status": "infra_failed",
                        "reward": None,
                        "exception_type": "VerifierTimeoutError",
                    },
                ]
            }
        },
    }
    assert normalize_task_vector(vector) == vector
    assert task_passed(vector, "task-a") is None


def test_invalid_task_vector_rejects_duplicate_trial_numbers() -> None:
    with pytest.raises(TaskVectorError, match="duplicate trial 0"):
        normalize_task_vector(
            {
                "schema_version": 1,
                "tasks": {
                    "task-a": {
                        "trials": [
                            {"trial": 0, "status": "complete", "reward": 1.0},
                            {"trial": 0, "status": "complete", "reward": 0.0},
                        ]
                    }
                },
            }
        )
