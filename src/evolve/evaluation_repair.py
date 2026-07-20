from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from .evaluation import EvaluationRecord, Outcome, TrialResult, classify_evaluation, effective_trial_outcome

_IDENTITY_FIELDS = (
    "experiment_id",
    "generation",
    "candidate_commit",
    "purpose",
    "evaluator_fingerprint",
    "task_set_hash",
    "runtime_fingerprint",
)


def repair_task_ids(record: EvaluationRecord) -> tuple[str, ...]:
    """Return tasks with explicit infrastructure-owned failed trial evidence."""
    return tuple(
        sorted(
            {
                trial.task_id
                for trial in record.trials
                if effective_trial_outcome(trial) is Outcome.INFRASTRUCTURE_FAILED
            }
        )
    )


def evaluation_record_from_payload(payload: dict[str, Any]) -> EvaluationRecord:
    trials = tuple(_trial_from_payload(raw) for raw in payload.get("trials", ()))
    return EvaluationRecord(
        experiment_id=str(payload["experiment_id"]),
        generation=str(payload["generation"]),
        candidate_commit=str(payload["candidate_commit"]),
        purpose=str(payload["purpose"]),
        attempt=int(payload["attempt"]),
        evaluator_fingerprint=str(payload["evaluator_fingerprint"]),
        task_set_hash=str(payload["task_set_hash"]),
        runtime_fingerprint=str(payload["runtime_fingerprint"]),
        expected_trials=int(payload["expected_trials"]),
        outcome=Outcome(str(payload["outcome"])),
        reason=str(payload.get("reason") or ""),
        trials=trials,
        score=float(payload["score"]) if payload.get("score") is not None else None,
        cost_usd=float(payload.get("cost_usd", 0.0)),
        wall_s=float(payload.get("wall_s", 0.0)),
        retry_of=int(payload["retry_of"]) if payload.get("retry_of") is not None else None,
        artifacts=dict(payload["artifacts"]) if isinstance(payload.get("artifacts"), dict) else None,
        source_attempts=tuple(int(value) for value in payload.get("source_attempts", ())),
        repaired_tasks=tuple(str(value) for value in payload.get("repaired_tasks", ())),
    )


def finalize_repair(
    workspace: Path,
    run_dir: Path,
    base: EvaluationRecord,
    repair: EvaluationRecord,
    *,
    benchmark_timeout_is_zero: bool,
) -> EvaluationRecord:
    _validate_identity(base, repair)
    target_tasks = set(repair_task_ids(base))
    repair_trials = {(trial.task_id, trial.trial): trial for trial in repair.trials}
    merged: list[TrialResult] = []
    replaced_slots: list[dict[str, object]] = []
    repaired_tasks: set[str] = set()
    for original in base.trials:
        source_attempt = original.source_attempt or base.attempt
        stamped_original = replace(original, source_attempt=source_attempt)
        key = (original.task_id, original.trial)
        replacement = repair_trials.get(key)
        if (
            replacement is None
            or original.task_id not in target_tasks
            or effective_trial_outcome(original) is not Outcome.INFRASTRUCTURE_FAILED
        ):
            merged.append(stamped_original)
            continue
        merged.append(
            replace(
                replacement,
                source_attempt=repair.attempt,
                repaired_from_attempt=source_attempt,
                repair_reason=_repair_reason(original),
            )
        )
        repaired_tasks.add(original.task_id)
        replaced_slots.append(
            {
                "task_id": original.task_id,
                "trial": original.trial,
                "from_attempt": source_attempt,
                "to_attempt": repair.attempt,
            }
        )
    result = classify_evaluation(
        experiment_id=base.experiment_id,
        generation=base.generation,
        candidate_commit=base.candidate_commit,
        purpose=base.purpose,
        attempt=repair.attempt,
        evaluator_fingerprint=base.evaluator_fingerprint,
        task_set_hash=base.task_set_hash,
        runtime_fingerprint=base.runtime_fingerprint,
        trials=tuple(merged),
        expected_trials=base.expected_trials,
        benchmark_timeout_is_zero=benchmark_timeout_is_zero,
        cost_usd=base.cost_usd + repair.cost_usd,
        wall_s=base.wall_s + repair.wall_s,
        retry_of=base.attempt,
        source_attempts=tuple(sorted({trial.source_attempt for trial in merged if trial.source_attempt is not None})),
        repaired_tasks=tuple(sorted(repaired_tasks)),
    )
    manifest = {
        "schema_version": 1,
        "kind": "failed_task_repair",
        "base_attempt": base.attempt,
        "repair_attempt": repair.attempt,
        "base_outcome": base.outcome.value,
        "base_reason": base.reason,
        "repair_outcome": repair.outcome.value,
        "repair_reason": repair.reason,
        "requested_tasks": sorted(target_tasks),
        "replaced_slots": replaced_slots,
        "base_artifacts": base.artifacts,
        "repair_artifacts": repair.artifacts,
    }
    path = run_dir / "composite_evaluation_artifacts.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    artifacts = {
        "path": path.relative_to(workspace).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    return replace(result, artifacts=artifacts)


def _validate_identity(base: EvaluationRecord, repair: EvaluationRecord) -> None:
    changed = [field for field in _IDENTITY_FIELDS if getattr(base, field) != getattr(repair, field)]
    if changed:
        raise RuntimeError(f"evaluation identity changed during failed-task repair: {', '.join(changed)}")


def _repair_reason(trial: TrialResult) -> str:
    details = ": ".join(value for value in (trial.exception_type, trial.exception_message) if value)
    return details or effective_trial_outcome(trial).value


def _trial_from_payload(raw: object) -> TrialResult:
    if not isinstance(raw, dict):
        raise ValueError("evaluation trial must be an object")
    data = cast("dict[str, Any]", raw)
    return TrialResult(
        task_id=str(data["task_id"]),
        trial=int(data["trial"]),
        outcome=Outcome(str(data["outcome"])),
        reward=float(data["reward"]) if data.get("reward") is not None else None,
        owner=str(data.get("owner") or "benchmark"),
        exception_type=str(data["exception_type"]) if data.get("exception_type") else None,
        exception_message=str(data["exception_message"]) if data.get("exception_message") else None,
        source_attempt=int(data["source_attempt"]) if data.get("source_attempt") is not None else None,
        repaired_from_attempt=(
            int(data["repaired_from_attempt"]) if data.get("repaired_from_attempt") is not None else None
        ),
        repair_reason=str(data["repair_reason"]) if data.get("repair_reason") else None,
    )
