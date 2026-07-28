from evolve.evaluation import EvaluationRecord, Outcome, TrialResult, classify_evaluation


def record_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "experiment_id": "exp",
        "generation": "7",
        "candidate_commit": "abc",
        "purpose": "candidate",
        "attempt": 1,
        "evaluator_fingerprint": "evaluator",
        "task_set_hash": "tasks",
        "runtime_fingerprint": "runtime",
        "cost_usd": 1.25,
        "wall_s": 3.0,
    }
    values.update(overrides)
    return values


def test_exception_beats_numeric_reward() -> None:
    trial = TrialResult(
        "task",
        0,
        Outcome.INFRASTRUCTURE_FAILED,
        0.0,
        "infrastructure",
        "ModuleNotFoundError",
    )

    record = classify_evaluation(**record_values(), trials=(trial,), expected_trials=1)

    assert isinstance(record, EvaluationRecord)
    assert record.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert record.score is None


def test_candidate_failure_beats_missing_trial_count() -> None:
    trial = TrialResult("task", 0, Outcome.CANDIDATE_INVALID, None, "candidate", "RuntimeError")

    record = classify_evaluation(**record_values(), trials=(trial,), expected_trials=60)

    assert record.outcome is Outcome.CANDIDATE_INVALID
    assert record.score is None


def test_candidate_wide_setup_failure_needs_no_trial_rows() -> None:
    record = classify_evaluation(
        **record_values(),
        trials=(),
        expected_trials=60,
        setup_outcome=Outcome.CANDIDATE_INVALID,
        setup_reason="candidate dependency setup failed",
    )

    assert record.outcome is Outcome.CANDIDATE_INVALID
    assert record.reason == "candidate dependency setup failed"
    assert record.score is None


def test_missing_evidence_is_infrastructure() -> None:
    record = classify_evaluation(**record_values(), trials=(), expected_trials=1)

    assert record.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert record.score is None


def test_complete_trials_are_the_only_scored_aggregate() -> None:
    trials = (
        TrialResult("a", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),
        TrialResult("b", 0, Outcome.BENCHMARK_COMPLETE, 0.0, "benchmark"),
    )

    record = classify_evaluation(**record_values(), trials=trials, expected_trials=2)

    assert record.outcome is Outcome.BENCHMARK_COMPLETE
    assert record.score == 0.5
    assert record.status == "complete"
    assert record.selection_eligible is True


def test_partial_evidence_is_scoreless_even_when_present_trials_have_rewards() -> None:
    trial = TrialResult("a", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark")

    record = classify_evaluation(**record_values(), trials=(trial,), expected_trials=2)

    assert record.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert record.score is None


def test_partial_floor_accepts_sparse_infrastructure_failures_conservatively() -> None:
    trials = tuple(
        TrialResult(f"task-{index}", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark")
        for index in range(48)
    ) + (
        TrialResult("task-48", 0, Outcome.INFRASTRUCTURE_FAILED, None, "ambiguous", "ProcessExit"),
        TrialResult("task-49", 0, Outcome.INFRASTRUCTURE_FAILED, None, "infrastructure", "MissingReward"),
    )

    record = classify_evaluation(
        **record_values(),
        trials=trials,
        expected_trials=50,
        partial_floor=0.8,
    )

    assert record.outcome is Outcome.BENCHMARK_COMPLETE
    assert record.score == 0.96
    assert record.selection_eligible is True
    assert record.reason == "partial evidence accepted: 48/50 scoreable trials"
    assert [trial.outcome for trial in record.trials[-2:]] == [
        Outcome.INFRASTRUCTURE_FAILED,
        Outcome.INFRASTRUCTURE_FAILED,
    ]


def test_partial_floor_rejects_systemically_missing_evidence() -> None:
    trials = (TrialResult("task-0", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),)

    record = classify_evaluation(
        **record_values(),
        trials=trials,
        expected_trials=100,
        partial_floor=0.8,
    )

    assert record.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert record.score is None


def test_unknown_exception_ownership_is_infrastructure() -> None:
    trial = TrialResult("a", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "unknown", "RuntimeError")

    record = classify_evaluation(**record_values(), trials=(trial,), expected_trials=1)

    assert record.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert record.score is None


def test_benchmark_agent_timeout_requires_explicit_zero_rule() -> None:
    trial = TrialResult("a", 0, Outcome.TIMEOUT, 0.0, "benchmark_agent")

    timeout = classify_evaluation(**record_values(), trials=(trial,), expected_trials=1)
    complete = classify_evaluation(
        **record_values(),
        trials=(trial,),
        expected_trials=1,
        benchmark_timeout_is_zero=True,
    )

    assert timeout.outcome is Outcome.TIMEOUT
    assert timeout.score is None
    assert complete.outcome is Outcome.BENCHMARK_COMPLETE
    assert complete.score == 0.0


def test_final_verifier_timeout_is_zero_despite_retained_exception_diagnostic() -> None:
    trial = TrialResult(
        "a",
        0,
        Outcome.TIMEOUT,
        0.0,
        "benchmark_verifier",
        "VerifierTimeoutError",
        "verifier exceeded deadline",
    )

    complete = classify_evaluation(
        **record_values(),
        trials=(trial,),
        expected_trials=1,
        benchmark_timeout_is_zero=True,
    )

    assert complete.outcome is Outcome.BENCHMARK_COMPLETE
    assert complete.score == 0.0


def test_genesis_complete_record_is_selection_eligible() -> None:
    trial = TrialResult("a", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark")

    record = classify_evaluation(
        **record_values(purpose="genesis"),
        trials=(trial,),
        expected_trials=1,
    )

    assert record.selection_eligible is True


def test_record_serializes_enums_as_plain_strings() -> None:
    trial = TrialResult("a", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark")

    payload = classify_evaluation(**record_values(), trials=(trial,), expected_trials=1).to_dict()

    assert payload["outcome"] == "benchmark_complete"
    assert payload["trials"][0]["outcome"] == "benchmark_complete"
