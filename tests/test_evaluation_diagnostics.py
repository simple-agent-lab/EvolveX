import json
from dataclasses import replace

from evolve.evaluation import (
    EvaluationRecord,
    Outcome,
    TrialIdentity,
    TrialResult,
    evaluation_diagnostics,
    materialize_missing_trials,
)


def test_materialize_missing_trials_uses_exact_contract_identities() -> None:
    expected = (
        TrialIdentity("task-a", 0, False, None),
        TrialIdentity("task-a", 1, False, None),
        TrialIdentity("task-b", 0, False, None),
    )
    observed = (
        TrialResult("task-a", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),
        TrialResult("task-b", 0, Outcome.CANDIDATE_INVALID, None, "candidate"),
    )

    trials = materialize_missing_trials(expected, observed)

    assert [(trial.task_id, trial.trial) for trial in trials] == [
        ("task-a", 0),
        ("task-a", 1),
        ("task-b", 0),
    ]
    missing = trials[1]
    assert missing.outcome is Outcome.MISSING
    assert missing.reward is None
    assert missing.owner == "evaluator"
    assert missing.failure_category == "missing"


def test_materialize_missing_trials_retains_unexpected_evidence_for_rejection() -> None:
    expected = (TrialIdentity("task-a", 0, False, None),)
    observed = (
        TrialResult("task-a", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),
        TrialResult("unexpected", 3, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),
    )

    trials = materialize_missing_trials(expected, observed)

    assert [(trial.task_id, trial.trial) for trial in trials] == [
        ("task-a", 0),
        ("unexpected", 3),
    ]


def test_materialize_missing_trials_accepts_unique_harbor_task_suffix() -> None:
    expected = (TrialIdentity("task-a", 0, False, None),)
    observed = (
        TrialResult(
            "registry/dataset__task-a",
            0,
            Outcome.BENCHMARK_COMPLETE,
            1.0,
            "benchmark",
        ),
    )

    trials = materialize_missing_trials(expected, observed)

    assert [(trial.task_id, trial.outcome) for trial in trials] == [
        ("task-a", Outcome.BENCHMARK_COMPLETE),
    ]


def test_materialize_missing_trials_rejects_ambiguous_harbor_task_suffix() -> None:
    expected = (
        TrialIdentity("task-a", 0, False, None),
        TrialIdentity("dataset__task-a", 0, False, None),
    )
    observed = (
        TrialResult(
            "registry__dataset__task-a",
            0,
            Outcome.BENCHMARK_COMPLETE,
            1.0,
            "benchmark",
        ),
    )

    trials = materialize_missing_trials(expected, observed)

    assert [trial.outcome for trial in trials[:2]] == [Outcome.MISSING, Outcome.MISSING]
    assert trials[2].task_id == "registry__dataset__task-a"


def _mixed_record() -> EvaluationRecord:
    return EvaluationRecord(
        experiment_id="exp",
        generation="7",
        candidate_commit="abc",
        purpose="candidate",
        attempt=1,
        evaluator_fingerprint="evaluator",
        task_set_hash="tasks",
        runtime_fingerprint="runtime",
        expected_trials=5,
        outcome=Outcome.CANDIDATE_INVALID,
        reason="candidate-owned trial failure",
        trials=(
            TrialResult("ok", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),
            TrialResult(
                "candidate",
                0,
                Outcome.CANDIDATE_INVALID,
                None,
                "candidate",
                exception_message="OPENAI_API_KEY=must-not-leak",
                failure_category="invalid_tool_history",
            ),
            TrialResult(
                "verifier",
                0,
                Outcome.INFRASTRUCTURE_FAILED,
                None,
                "evaluator",
                exception_message="https_proxy=http://must-not-leak",
                failure_category="verifier_dependency_download",
            ),
            TrialResult("timeout", 0, Outcome.TIMEOUT, 0.0, "benchmark_verifier"),
            TrialResult(
                "absent",
                0,
                Outcome.MISSING,
                None,
                "evaluator",
                failure_category="missing",
            ),
        ),
        score=None,
        cost_usd=1.0,
        wall_s=2.0,
        contract_id="a" * 64,
        contract_certified=True,
        scoreable_trials=1,
        artifacts={"path": "runs/evaluations/artifacts.json", "sha256": "b" * 64},
        evaluation_contract={"path": "runs/evaluation-contract.json", "sha256": "c" * 64},
        preflight_receipt={"path": "runs/preflight.json", "sha256": "e" * 64},
        candidate_runtime={"path": "/private/runtime.json", "sha256": "d" * 64},
    )


def test_evaluation_diagnostics_is_exact_bounded_and_safe() -> None:
    diagnostics = evaluation_diagnostics(_mixed_record()).to_dict()

    assert diagnostics == {
        "schema_version": 1,
        "contract_id": "a" * 64,
        "purpose": "candidate",
        "expected_trials": 5,
        "observed_trials": 4,
        "scoreable_trials": 1,
        "missing_trials": 1,
        "outcome_counts": {
            "benchmark_complete": 1,
            "candidate_invalid": 1,
            "infrastructure_failed": 1,
            "missing": 1,
            "timeout": 1,
        },
        "owner_counts": {
            "benchmark": 1,
            "benchmark_verifier": 1,
            "candidate": 1,
            "evaluator": 2,
        },
        "timeouts_by_owner": {"benchmark_verifier": 1},
        "failures": [
            {
                "category": "benchmark_verifier_timeout",
                "owner": "benchmark_verifier",
                "count": 1,
                "actionable": False,
            },
            {
                "category": "invalid_tool_history",
                "owner": "candidate",
                "count": 1,
                "actionable": True,
            },
            {
                "category": "missing",
                "owner": "evaluator",
                "count": 1,
                "actionable": False,
            },
            {
                "category": "verifier_dependency_download",
                "owner": "evaluator",
                "count": 1,
                "actionable": False,
            },
        ],
        "retry_eligible": False,
        "contract_certified": True,
        "artifact_references": [
            {"kind": "artifacts", "path": "runs/evaluations/artifacts.json", "sha256": "b" * 64},
            {
                "kind": "evaluation_contract",
                "path": "runs/evaluation-contract.json",
                "sha256": "c" * 64,
            },
            {"kind": "preflight_receipt", "path": "runs/preflight.json", "sha256": "e" * 64},
        ],
    }
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "must-not-leak" not in serialized
    assert "/private/runtime.json" not in serialized


def test_anchor_diagnostics_never_marks_candidate_failures_actionable() -> None:
    diagnostics = evaluation_diagnostics(replace(_mixed_record(), purpose="anchor"))

    assert not any(failure.actionable for failure in diagnostics.failures)


def test_failure_category_limit_is_deterministic() -> None:
    record = replace(
        _mixed_record(),
        trials=(
            TrialResult("z", 0, Outcome.INFRASTRUCTURE_FAILED, None, "evaluator", failure_category="zeta"),
            TrialResult("a", 0, Outcome.INFRASTRUCTURE_FAILED, None, "evaluator", failure_category="alpha"),
            TrialResult("b", 0, Outcome.INFRASTRUCTURE_FAILED, None, "evaluator", failure_category="beta"),
        ),
        expected_trials=3,
        scoreable_trials=0,
    )

    diagnostics = evaluation_diagnostics(record, max_failure_categories=2)

    assert [failure.category for failure in diagnostics.failures] == ["alpha", "beta"]
