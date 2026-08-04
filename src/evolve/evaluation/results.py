from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class Outcome(StrEnum):
    BENCHMARK_COMPLETE = "benchmark_complete"
    CANDIDATE_INVALID = "candidate_invalid"
    INFRASTRUCTURE_FAILED = "infrastructure_failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


CANONICAL_OUTCOMES = frozenset(outcome.value for outcome in Outcome)


def evaluation_status(values: dict[str, Any]) -> str | None:
    outcome = values.get("outcome")
    if outcome == Outcome.BENCHMARK_COMPLETE:
        return "complete"
    status = values.get("status")
    return str(outcome or status) if outcome in CANONICAL_OUTCOMES or status is not None else None


@dataclass(frozen=True)
class TrialResult:
    task_id: str
    trial: int
    outcome: Outcome
    reward: float | None
    owner: str
    exception_type: str | None = None
    exception_message: str | None = None
    source_attempt: int | None = None
    repaired_from_attempt: int | None = None
    repair_reason: str | None = None

    def __post_init__(self) -> None:
        if self.reward is not None and (
            isinstance(self.reward, bool)
            or not isinstance(self.reward, (int, float))
            or not math.isfinite(float(self.reward))
        ):
            raise ValueError("trial reward must be a finite number or null")

    def score_eligible(self, *, benchmark_timeout_is_zero: bool) -> bool:
        return (
            self.reward is not None
            and math.isfinite(float(self.reward))
            and (
                self.outcome is Outcome.BENCHMARK_COMPLETE
                or (
                    self.outcome is Outcome.TIMEOUT
                    and self.owner in {"benchmark_agent", "benchmark_verifier"}
                    and benchmark_timeout_is_zero
                )
            )
        )


@dataclass(frozen=True)
class EvaluationRecord:
    experiment_id: str
    generation: str
    candidate_commit: str
    purpose: str
    attempt: int
    evaluator_fingerprint: str
    task_set_hash: str
    runtime_fingerprint: str
    expected_trials: int
    outcome: Outcome
    reason: str
    trials: tuple[TrialResult, ...]
    score: float | None
    cost_usd: float
    wall_s: float
    retry_of: int | None = None
    artifacts: dict[str, str] | None = None
    source_attempts: tuple[int, ...] = ()
    repaired_tasks: tuple[str, ...] = ()
    candidate_runtime: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.score is not None and (
            isinstance(self.score, bool)
            or not isinstance(self.score, (int, float))
            or not math.isfinite(float(self.score))
        ):
            raise ValueError("evaluation score must be a finite number or null")
        for field, value in (("cost_usd", self.cost_usd), ("wall_s", self.wall_s)):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0
            ):
                raise ValueError(f"{field} must be a finite non-negative number")

    @property
    def status(self) -> str:
        return "complete" if self.outcome is Outcome.BENCHMARK_COMPLETE else self.outcome.value

    @property
    def selection_eligible(self) -> bool:
        return self.outcome is Outcome.BENCHMARK_COMPLETE and self.purpose in {"candidate", "genesis"}

    def to_dict(self) -> dict[str, object]:
        payload = {
            **asdict(self),
            "outcome": self.outcome.value,
            "trials": [_trial_payload(trial) for trial in self.trials],
        }
        if not self.source_attempts:
            payload.pop("source_attempts")
        if not self.repaired_tasks:
            payload.pop("repaired_tasks")
        return payload


def _trial_payload(trial: TrialResult) -> dict[str, object]:
    payload = {**asdict(trial), "outcome": trial.outcome.value}
    for field in ("source_attempt", "repaired_from_attempt", "repair_reason"):
        if payload[field] is None:
            payload.pop(field)
    return payload


def effective_trial_outcome(trial: TrialResult) -> Outcome:
    if trial.outcome is Outcome.TIMEOUT and trial.owner in {"benchmark_agent", "benchmark_verifier"}:
        return Outcome.TIMEOUT
    if trial.exception_type or trial.exception_message:
        return Outcome.CANDIDATE_INVALID if trial.owner == "candidate" else Outcome.INFRASTRUCTURE_FAILED
    if trial.outcome is Outcome.CANDIDATE_INVALID and trial.owner != "candidate":
        return Outcome.INFRASTRUCTURE_FAILED
    return trial.outcome


def classify_evaluation(
    *,
    trials: tuple[TrialResult, ...],
    expected_trials: int,
    partial_floor: float = 1.0,
    benchmark_timeout_is_zero: bool = False,
    setup_outcome: Outcome | None = None,
    setup_reason: str | None = None,
    **values: Any,
) -> EvaluationRecord:
    if expected_trials < 1:
        raise ValueError("expected_trials must be at least 1")
    if not 0 < partial_floor <= 1:
        raise ValueError("partial_floor must be greater than zero and at most one")
    if any(trial.reward is not None and not math.isfinite(float(trial.reward)) for trial in trials):
        raise ValueError("trial rewards must be finite")
    outcomes = tuple(effective_trial_outcome(trial) for trial in trials)
    if setup_outcome is not None:
        outcomes = (setup_outcome, *outcomes)
    scoreable = tuple(
        trial
        for trial in trials
        if effective_trial_outcome(trial) not in {Outcome.INFRASTRUCTURE_FAILED, Outcome.CANDIDATE_INVALID}
        and trial.score_eligible(benchmark_timeout_is_zero=benchmark_timeout_is_zero)
    )
    coverage = len(scoreable) / expected_trials
    if setup_outcome is Outcome.INFRASTRUCTURE_FAILED:
        outcome = Outcome.INFRASTRUCTURE_FAILED
        reason = setup_reason or "evaluation infrastructure failed"
    elif Outcome.CANDIDATE_INVALID in outcomes:
        outcome = Outcome.CANDIDATE_INVALID
        reason = (
            setup_reason
            if setup_outcome is Outcome.CANDIDATE_INVALID and setup_reason
            else "candidate-owned trial failure"
        )
    elif Outcome.CANCELLED in outcomes:
        outcome, reason = Outcome.CANCELLED, setup_reason or "evaluation cancelled"
    elif len(trials) > expected_trials:
        outcome, reason = Outcome.INFRASTRUCTURE_FAILED, "unexpected extra trial evidence"
    elif scoreable and coverage >= partial_floor:
        outcome = Outcome.BENCHMARK_COMPLETE
        reason = (
            "all required trials are scoreable"
            if len(scoreable) == expected_trials and len(trials) == expected_trials
            else f"partial evidence accepted: {len(scoreable)}/{expected_trials} scoreable trials"
        )
    elif Outcome.INFRASTRUCTURE_FAILED in outcomes or not trials or len(trials) != expected_trials:
        outcome, reason = Outcome.INFRASTRUCTURE_FAILED, "insufficient scoreable trial evidence"
    else:
        outcome, reason = Outcome.TIMEOUT, "non-scoreable timeout"
    score = (
        sum(float(trial.reward) for trial in scoreable if trial.reward is not None) / expected_trials
        if outcome is Outcome.BENCHMARK_COMPLETE
        else None
    )
    return EvaluationRecord(
        **values, expected_trials=expected_trials, trials=trials, outcome=outcome, reason=reason, score=score
    )
