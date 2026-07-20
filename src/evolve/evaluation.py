from __future__ import annotations

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

    def score_eligible(self, *, benchmark_timeout_is_zero: bool) -> bool:
        return self.reward is not None and (
            self.outcome is Outcome.BENCHMARK_COMPLETE
            or (
                self.outcome is Outcome.TIMEOUT
                and self.owner in {"benchmark_agent", "benchmark_verifier"}
                and benchmark_timeout_is_zero
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
    candidate_runtime: dict[str, str] | None = None

    @property
    def status(self) -> str:
        return "complete" if self.outcome is Outcome.BENCHMARK_COMPLETE else self.outcome.value

    @property
    def selection_eligible(self) -> bool:
        return self.outcome is Outcome.BENCHMARK_COMPLETE and self.purpose in {"candidate", "genesis"}

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "outcome": self.outcome.value,
            "trials": [{**asdict(trial), "outcome": trial.outcome.value} for trial in self.trials],
        }


class EvaluationInterrupted(BaseException):
    """Carries a cancelled attempt to the driver for append-before-reraise."""


def _effective_outcome(trial: TrialResult) -> Outcome:
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
    benchmark_timeout_is_zero: bool = False,
    setup_outcome: Outcome | None = None,
    setup_reason: str | None = None,
    **values: Any,
) -> EvaluationRecord:
    outcomes = tuple(_effective_outcome(trial) for trial in trials)
    if setup_outcome is not None:
        outcomes = (setup_outcome, *outcomes)
    if Outcome.INFRASTRUCTURE_FAILED in outcomes:
        outcome = Outcome.INFRASTRUCTURE_FAILED
        reason = (
            setup_reason
            if setup_outcome is Outcome.INFRASTRUCTURE_FAILED and setup_reason
            else "infrastructure-owned trial failure"
        )
    elif Outcome.CANDIDATE_INVALID in outcomes:
        outcome = Outcome.CANDIDATE_INVALID
        reason = (
            setup_reason
            if setup_outcome is Outcome.CANDIDATE_INVALID and setup_reason
            else "candidate-owned trial failure"
        )
    elif Outcome.CANCELLED in outcomes:
        outcome, reason = Outcome.CANCELLED, setup_reason or "evaluation cancelled"
    elif not trials or len(trials) != expected_trials:
        outcome, reason = Outcome.INFRASTRUCTURE_FAILED, "missing required trial evidence"
    elif all(trial.score_eligible(benchmark_timeout_is_zero=benchmark_timeout_is_zero) for trial in trials):
        outcome, reason = Outcome.BENCHMARK_COMPLETE, "all required trials are scoreable"
    else:
        outcome, reason = Outcome.TIMEOUT, "non-scoreable timeout"
    score = (
        sum(float(trial.reward) for trial in trials if trial.reward is not None) / len(trials)
        if outcome is Outcome.BENCHMARK_COMPLETE
        else None
    )
    return EvaluationRecord(
        **values, expected_trials=expected_trials, trials=trials, outcome=outcome, reason=reason, score=score
    )
