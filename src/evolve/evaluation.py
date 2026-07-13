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
        if self.reward is None:
            return False
        return self.outcome is Outcome.BENCHMARK_COMPLETE or (
            self.outcome is Outcome.TIMEOUT
            and self.owner == "benchmark_agent"
            and benchmark_timeout_is_zero
        )


@dataclass(frozen=True)
class EvaluationCertificate:
    experiment_id: str
    epoch: int
    generation: str
    candidate_id: str
    purpose: str
    attempt: int
    evaluator_fingerprint: str
    candidate_fingerprint: str
    task_set_hash: str
    expected_trials: int
    outcome: Outcome
    reason: str
    trials: tuple[TrialResult, ...]
    score: float | None
    selection_eligible: bool
    retryable: bool
    cost_usd: float
    wall_s: float
    retry_of: int | None = None
    evaluation_artifacts: dict[str, str] | None = None
    provenance: dict[str, str] | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        payload["trials"] = [{**asdict(trial), "outcome": trial.outcome.value} for trial in self.trials]
        return payload


def _effective_outcome(trial: TrialResult) -> Outcome:
    if trial.exception_type or trial.exception_message:
        return Outcome.CANDIDATE_INVALID if trial.owner == "candidate" else Outcome.INFRASTRUCTURE_FAILED
    return trial.outcome


def certify_evaluation(*, benchmark_timeout_is_zero: bool = False, **values: Any) -> EvaluationCertificate:
    trials = tuple(values.pop("trials"))
    expected_trials = int(values["expected_trials"])
    outcomes = tuple(_effective_outcome(trial) for trial in trials)
    if len(trials) != expected_trials:
        outcome, reason = Outcome.INFRASTRUCTURE_FAILED, "missing required trial evidence"
    elif Outcome.INFRASTRUCTURE_FAILED in outcomes:
        failed = trials[outcomes.index(Outcome.INFRASTRUCTURE_FAILED)]
        outcome = Outcome.INFRASTRUCTURE_FAILED
        reason = f"{failed.owner}:{failed.exception_type or 'trial_failed'}"
    elif Outcome.CANDIDATE_INVALID in outcomes:
        outcome, reason = Outcome.CANDIDATE_INVALID, "candidate trial invalid"
    elif Outcome.CANCELLED in outcomes:
        outcome, reason = Outcome.CANCELLED, "evaluation cancelled"
    elif all(trial.score_eligible(benchmark_timeout_is_zero=benchmark_timeout_is_zero) for trial in trials):
        outcome, reason = Outcome.BENCHMARK_COMPLETE, "all required trials are score-eligible"
    else:
        outcome, reason = Outcome.TIMEOUT, "non-score-eligible timeout"
    score = None
    if outcome is Outcome.BENCHMARK_COMPLETE:
        score = sum(float(trial.reward) for trial in trials if trial.reward is not None) / len(trials)
    return EvaluationCertificate(
        **values,
        trials=trials,
        outcome=outcome,
        reason=reason,
        score=score,
        selection_eligible=outcome is Outcome.BENCHMARK_COMPLETE and values["purpose"] == "candidate",
        retryable=outcome is Outcome.INFRASTRUCTURE_FAILED,
    )
