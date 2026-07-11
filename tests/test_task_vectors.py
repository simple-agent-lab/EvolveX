import json
import subprocess
import sys
from pathlib import Path

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
                            {"trial": True, "status": "complete", "reward": 1.0},
                        ]
                    }
                },
            }
        )


@pytest.mark.parametrize(
    ("status", "reward", "message"),
    [
        ("complete", None, "complete trial.*numeric reward"),
        ("agent_timeout", 0.0, "non-complete trial.*null reward"),
        ("infra_failed", 1.0, "non-complete trial.*null reward"),
        ("cancelled", 0.0, "non-complete trial.*null reward"),
    ],
)
def test_invalid_task_vector_rejects_inconsistent_status_reward(status: str, reward: float | None, message: str) -> None:
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


def test_stub_eval_emits_configured_completed_trials_without_changing_score(tmp_path: Path) -> None:
    evaluator_dir = tmp_path / "evaluator"
    evaluator_dir.mkdir()
    (evaluator_dir / "eval.env").write_text("EVOLVE_HARBOR_ATTEMPTS=3\n")
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "agent.py").write_text("# FAIL task-0\n")
    run_dir = tmp_path / "run"
    script = Path(__file__).resolve().parents[1] / "templates" / "evaluator" / "stub_eval.py"

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
        assert all(trial["status"] == "complete" for trial in task["trials"])
    artifacts = json.loads((run_dir / "evaluation_artifacts.json").read_text())
    assert len(artifacts["trials"]) == 8 * 3
    assert all((run_dir / "artifacts" / trial["files"][0]["path"]).is_file() for trial in artifacts["trials"])
