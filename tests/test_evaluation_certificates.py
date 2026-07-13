from evolve.evaluation import Outcome, TrialResult, certify_evaluation


def _certificate(*trials: TrialResult, expected_trials: int | None = None, **overrides):
    values = {
        "experiment_id": "exp",
        "epoch": 0,
        "generation": "7",
        "candidate_id": "abc",
        "purpose": "candidate",
        "attempt": 1,
        "evaluator_fingerprint": "runtime",
        "candidate_fingerprint": "candidate",
        "task_set_hash": "tasks",
        "expected_trials": len(trials) if expected_trials is None else expected_trials,
        "trials": trials,
        "cost_usd": 1.25,
        "wall_s": 3.0,
    }
    values.update(overrides)
    return certify_evaluation(**values)


def test_exception_reward_is_not_score_eligible() -> None:
    trial = TrialResult(
        task_id="task-a",
        trial=0,
        outcome=Outcome.INFRASTRUCTURE_FAILED,
        reward=0.0,
        owner="evaluator",
        exception_type="ModuleNotFoundError",
        exception_message="No module named 'fastapi'",
    )

    certificate = _certificate(trial)

    assert certificate.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert certificate.reason == "evaluator:ModuleNotFoundError"
    assert certificate.score is None
    assert certificate.selection_eligible is False
    assert certificate.retryable is True


def test_exception_fields_override_a_misreported_complete_outcome() -> None:
    trial = TrialResult(
        task_id="task-a",
        trial=0,
        outcome=Outcome.BENCHMARK_COMPLETE,
        reward=0.0,
        owner="evaluator",
        exception_type="NonZeroAgentExitCodeError",
        exception_message="ModuleNotFoundError: No module named 'fastapi'",
    )

    certificate = _certificate(trial)

    assert certificate.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert certificate.score is None
    assert certificate.selection_eligible is False


def test_benchmark_agent_timeout_is_valid_zero_when_contract_allows_it() -> None:
    trial = TrialResult(
        task_id="task-a",
        trial=0,
        outcome=Outcome.TIMEOUT,
        reward=0.0,
        owner="benchmark_agent",
    )

    certificate = _certificate(trial, benchmark_timeout_is_zero=True)

    assert certificate.outcome is Outcome.BENCHMARK_COMPLETE
    assert certificate.score == 0.0
    assert certificate.selection_eligible is True


def test_missing_trial_evidence_is_infrastructure_failure() -> None:
    certificate = _certificate(expected_trials=1)

    assert certificate.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert certificate.reason == "missing required trial evidence"
    assert certificate.score is None
    assert certificate.retryable is True


def test_candidate_invalid_precedes_cancelled_and_is_not_retryable() -> None:
    invalid = TrialResult("task-a", 0, Outcome.CANDIDATE_INVALID, None, "candidate")
    cancelled = TrialResult("task-b", 0, Outcome.CANCELLED, None, "experiment")

    certificate = _certificate(invalid, cancelled)

    assert certificate.outcome is Outcome.CANDIDATE_INVALID
    assert certificate.selection_eligible is False
    assert certificate.retryable is False


def test_non_candidate_purpose_is_never_selection_eligible() -> None:
    complete = TrialResult("task-a", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark")

    certificate = _certificate(complete, purpose="canary")

    assert certificate.outcome is Outcome.BENCHMARK_COMPLETE
    assert certificate.score == 1.0
    assert certificate.selection_eligible is False


def test_certificate_serializes_enums_as_plain_strings() -> None:
    complete = TrialResult("task-a", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark")

    payload = _certificate(complete).to_dict()

    assert payload["outcome"] == "benchmark_complete"
    assert payload["trials"][0]["outcome"] == "benchmark_complete"
