from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from evolve.evaluation.identity import effective_task_set_identity
from evolve.evaluation.run_plan import EvaluationRunPlan


def _plan() -> EvaluationRunPlan:
    return EvaluationRunPlan(
        schema_version=1,
        experiment_id="experiment",
        generation="3",
        candidate_commit="a" * 40,
        purpose="candidate",
        canonical=True,
        tasks=("task-a", "task-b"),
        attempts_per_task=2,
        expected_trials=4,
        concurrency=2,
        evaluator_fingerprint="b" * 40,
        task_set_hash="c" * 64,
        runtime_fingerprint="d" * 64,
        execution_runtime_fingerprint="e" * 64,
    )


def test_run_plan_round_trips_as_authoritative_evaluation_input(tmp_path: Path) -> None:
    path = _plan().write(tmp_path / "run-plan.json")

    assert EvaluationRunPlan.read(path) == _plan()
    assert json.loads(path.read_text())["tasks"] == ["task-a", "task-b"]


def test_run_plan_rejects_trial_count_drift(tmp_path: Path) -> None:
    path = replace(_plan(), expected_trials=3).write(tmp_path / "run-plan.json")

    with pytest.raises(ValueError, match="does not match"):
        EvaluationRunPlan.read(path)


def test_task_limit_changes_both_members_and_identity(tmp_path: Path) -> None:
    evaluator = tmp_path / "evaluator"
    evaluator.mkdir()
    (evaluator / "splits.json").write_text(
        json.dumps(
            {
                "version": 2,
                "resolved": True,
                "tasks": {"train": [], "gate": ["task-c", "task-a", "task-b"], "sealed": []},
                "task_digests": {"task-a": "a", "task-b": "b", "task-c": "c"},
            }
        )
    )
    config = {"dataset": "local", "k": 2, "evaluation_split": "gate"}

    full = effective_task_set_identity(tmp_path, config)
    limited = effective_task_set_identity(tmp_path, config, task_limit=1)

    assert full.members == ("task-a", "task-b", "task-c")
    assert limited.members == ("task-a",)
    assert limited.digest != full.digest


def test_gate_identity_uses_the_frozen_per_round_limit(tmp_path: Path) -> None:
    evaluator = tmp_path / "evaluator"
    evaluator.mkdir()
    (evaluator / "splits.json").write_text(
        json.dumps(
            {
                "version": 2,
                "resolved": True,
                "sampling": "static",
                "gate_tasks_per_round": 2,
                "tasks": {"train": [], "gate": ["task-c", "task-a", "task-b"], "sealed": []},
                "task_digests": {"task-a": "a", "task-b": "b", "task-c": "c"},
            }
        )
    )

    identity = effective_task_set_identity(
        tmp_path,
        {"dataset": "local", "k": 1, "evaluation_split": "gate"},
    )

    assert identity.members == ("task-a", "task-c")
