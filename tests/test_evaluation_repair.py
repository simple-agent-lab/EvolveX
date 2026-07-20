import json
from pathlib import Path

from evolve.evaluation import EvaluationRecord, Outcome, TrialResult
from evolve.evaluation_repair import finalize_repair, repair_task_ids


def _record(
    attempt: int,
    trials: tuple[TrialResult, ...],
    outcome: Outcome,
    *,
    cost: float,
    artifacts: dict[str, str],
) -> EvaluationRecord:
    return EvaluationRecord(
        experiment_id="exp",
        generation="1",
        candidate_commit="abc",
        purpose="candidate",
        attempt=attempt,
        evaluator_fingerprint="evaluator",
        task_set_hash="tasks",
        runtime_fingerprint="runtime",
        expected_trials=3,
        outcome=outcome,
        reason=outcome.value,
        trials=trials,
        score=None,
        cost_usd=cost,
        wall_s=float(attempt),
        retry_of=1 if attempt == 2 else None,
        artifacts=artifacts,
    )


def test_failed_task_repair_preserves_successful_slots_and_attempt_provenance(tmp_path: Path) -> None:
    base = _record(
        1,
        (
            TrialResult("task-a", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),
            TrialResult("task-b", 0, Outcome.BENCHMARK_COMPLETE, 0.0, "benchmark"),
            TrialResult(
                "task-c",
                0,
                Outcome.INFRASTRUCTURE_FAILED,
                None,
                "infrastructure",
                "ConnectionError",
                "upstream reset",
            ),
        ),
        Outcome.INFRASTRUCTURE_FAILED,
        cost=3.0,
        artifacts={"path": "attempt-1/evaluation_artifacts.json", "sha256": "one"},
    )
    repair = _record(
        2,
        (TrialResult("task-c", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),),
        Outcome.BENCHMARK_COMPLETE,
        cost=1.0,
        artifacts={"path": "attempt-2/evaluation_artifacts.json", "sha256": "two"},
    )
    workspace = tmp_path / "workspace"
    run_dir = workspace / "runs/evaluations/candidate/gen-1/commit/attempt-2"
    run_dir.mkdir(parents=True)

    result = finalize_repair(workspace, run_dir, base, repair, benchmark_timeout_is_zero=False)

    assert repair_task_ids(base) == ("task-c",)
    assert result.outcome is Outcome.BENCHMARK_COMPLETE
    assert result.score == 2 / 3
    assert result.cost_usd == 4.0
    assert result.retry_of == 1
    assert result.source_attempts == (1, 2)
    assert result.repaired_tasks == ("task-c",)
    assert [(trial.task_id, trial.source_attempt) for trial in result.trials] == [
        ("task-a", 1),
        ("task-b", 1),
        ("task-c", 2),
    ]
    repaired = result.trials[-1]
    assert repaired.repaired_from_attempt == 1
    assert repaired.repair_reason == "ConnectionError: upstream reset"
    manifest = json.loads((run_dir / "composite_evaluation_artifacts.json").read_text())
    assert manifest["requested_tasks"] == ["task-c"]
    assert manifest["replaced_slots"] == [{"task_id": "task-c", "trial": 0, "from_attempt": 1, "to_attempt": 2}]


def test_repair_does_not_replace_a_successful_sibling_trial_from_same_task(tmp_path: Path) -> None:
    base = _record(
        1,
        (
            TrialResult("task-a", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),
            TrialResult("task-a", 1, Outcome.INFRASTRUCTURE_FAILED, None, "evaluator"),
            TrialResult("task-b", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),
        ),
        Outcome.INFRASTRUCTURE_FAILED,
        cost=0.0,
        artifacts={},
    )
    repair = _record(
        2,
        (
            TrialResult("task-a", 0, Outcome.BENCHMARK_COMPLETE, 0.0, "benchmark"),
            TrialResult("task-a", 1, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),
        ),
        Outcome.BENCHMARK_COMPLETE,
        cost=0.0,
        artifacts={},
    )
    workspace = tmp_path / "workspace"
    run_dir = workspace / "runs/attempt-2"
    run_dir.mkdir(parents=True)

    result = finalize_repair(workspace, run_dir, base, repair, benchmark_timeout_is_zero=False)

    assert [(trial.trial, trial.reward, trial.source_attempt) for trial in result.trials[:2]] == [
        (0, 1.0, 1),
        (1, 1.0, 2),
    ]
