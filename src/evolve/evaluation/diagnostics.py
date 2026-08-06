from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Any, cast

from .contract import EvaluationContractV1, TrialIdentity
from .results import EvaluationRecord, Outcome, TrialResult

_SAFE_SLUG = re.compile(r"[a-z0-9_]{1,64}")
_SAFE_SHA256 = re.compile(r"[a-f0-9]{64}")
_KNOWN_OWNERS = frozenset(
    {
        "ambiguous",
        "benchmark",
        "benchmark_agent",
        "benchmark_verifier",
        "candidate",
        "evaluator",
        "infrastructure",
    }
)
_ACTIONABLE_PURPOSES = frozenset({"candidate", "genesis"})
_SAFE_DIAGNOSTIC_SLUG = re.compile(r"[a-z0-9_]{1,64}")
_SAFE_DIAGNOSTIC_SHA = re.compile(r"[a-f0-9]{64}")


class DiagnosticsValidationError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(message)


PayloadValidationError = DiagnosticsValidationError


@dataclass(frozen=True)
class FailureDiagnosticV1:
    category: str
    owner: str
    count: int
    actionable: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "owner": self.owner,
            "count": self.count,
            "actionable": self.actionable,
        }


@dataclass(frozen=True)
class EvaluationDiagnosticsV1:
    schema_version: int
    contract_id: str | None
    purpose: str
    expected_trials: int
    observed_trials: int
    scoreable_trials: int
    missing_trials: int
    outcome_counts: dict[str, int]
    owner_counts: dict[str, int]
    timeouts_by_owner: dict[str, int]
    failures: tuple[FailureDiagnosticV1, ...]
    retry_eligible: bool
    contract_certified: bool
    artifact_references: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "purpose": self.purpose,
            "expected_trials": self.expected_trials,
            "observed_trials": self.observed_trials,
            "scoreable_trials": self.scoreable_trials,
            "missing_trials": self.missing_trials,
            "outcome_counts": dict(self.outcome_counts),
            "owner_counts": dict(self.owner_counts),
            "timeouts_by_owner": dict(self.timeouts_by_owner),
            "failures": [failure.to_dict() for failure in self.failures],
            "retry_eligible": self.retry_eligible,
            "contract_certified": self.contract_certified,
            "artifact_references": [dict(reference) for reference in self.artifact_references],
        }


def materialize_missing_trials(
    expected: tuple[TrialIdentity, ...],
    observed: tuple[TrialResult, ...],
) -> tuple[TrialResult, ...]:
    """Return contract-ordered evidence with explicit rows for absent trials."""
    expected_task_ids = {trial.task_id for trial in expected}
    normalized_observed = tuple(_normalize_harbor_task_id(trial, expected_task_ids) for trial in observed)
    observed_by_identity = {(trial.task_id, trial.trial): trial for trial in normalized_observed}
    expected_identities = {(trial.task_id, trial.repetition) for trial in expected}
    materialized = tuple(
        observed_by_identity.get(
            (identity.task_id, identity.repetition),
            TrialResult(
                task_id=identity.task_id,
                trial=identity.repetition,
                outcome=Outcome.MISSING,
                reward=None,
                owner="evaluator",
                failure_category="missing",
            ),
        )
        for identity in expected
    )
    unexpected = tuple(
        trial for trial in normalized_observed if (trial.task_id, trial.trial) not in expected_identities
    )
    return (*materialized, *unexpected)


def _normalize_harbor_task_id(trial: TrialResult, expected_task_ids: set[str]) -> TrialResult:
    if trial.task_id in expected_task_ids:
        return trial
    matches = [task_id for task_id in expected_task_ids if trial.task_id.endswith(f"__{task_id}")]
    return replace(trial, task_id=matches[0]) if len(matches) == 1 else trial


def materialize_setup_failure(
    expected: tuple[TrialIdentity, ...],
    outcome: Outcome,
    *,
    failure_category: str,
) -> tuple[TrialResult, ...]:
    if outcome is not Outcome.CANDIDATE_INVALID:
        return materialize_missing_trials(expected, ())
    return tuple(
        TrialResult(
            task_id=identity.task_id,
            trial=identity.repetition,
            outcome=outcome,
            reward=None,
            owner="candidate",
            failure_category=failure_category,
        )
        for identity in expected
    )


def contract_trials(
    contract: EvaluationContractV1 | None,
    trials: tuple[TrialResult, ...],
) -> tuple[TrialResult, ...]:
    return materialize_missing_trials(contract.trial_identities, trials) if contract is not None else trials


def freeze_diagnostics(
    record: EvaluationRecord,
    contract: EvaluationContractV1 | None,
) -> EvaluationRecord:
    if contract is None:
        return record
    return replace(record, diagnostics=evaluation_diagnostics(record).to_dict())


def evaluation_diagnostics(
    record: EvaluationRecord,
    *,
    max_failure_categories: int = 16,
) -> EvaluationDiagnosticsV1:
    if max_failure_categories < 1:
        raise ValueError("max_failure_categories must be at least 1")
    outcomes = Counter(trial.outcome.value for trial in record.trials)
    owners = Counter(_safe_owner(trial.owner) for trial in record.trials)
    timeouts = Counter(_safe_owner(trial.owner) for trial in record.trials if trial.outcome is Outcome.TIMEOUT)
    grouped: Counter[tuple[str, str, bool]] = Counter()
    for trial in record.trials:
        if trial.outcome is Outcome.BENCHMARK_COMPLETE:
            continue
        owner = _safe_owner(trial.owner)
        actionable = owner == "candidate" and record.purpose in _ACTIONABLE_PURPOSES
        grouped[(_failure_category(trial, owner), owner, actionable)] += 1
    failures = tuple(
        FailureDiagnosticV1(category, owner, count, actionable)
        for (category, owner, actionable), count in sorted(grouped.items(), key=lambda item: (-item[1], item[0]))[
            :max_failure_categories
        ]
    )
    missing = outcomes[Outcome.MISSING.value]
    return EvaluationDiagnosticsV1(
        schema_version=1,
        contract_id=record.contract_id,
        purpose=record.purpose,
        expected_trials=record.expected_trials,
        observed_trials=len(record.trials) - missing,
        scoreable_trials=record.scoreable_trials,
        missing_trials=missing,
        outcome_counts=dict(sorted(outcomes.items())),
        owner_counts=dict(sorted(owners.items())),
        timeouts_by_owner=dict(sorted(timeouts.items())),
        failures=failures,
        retry_eligible=record.outcome
        in {Outcome.INFRASTRUCTURE_FAILED, Outcome.TIMEOUT, Outcome.CANCELLED, Outcome.MISSING},
        contract_certified=record.contract_certified,
        artifact_references=_artifact_references(record),
    )


def validate_evaluation_diagnostics_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PayloadValidationError("diagnostics", "diagnostics must be a JSON object")
    data = cast(dict[str, Any], payload)
    if data.get("schema_version") != 1:
        raise PayloadValidationError("diagnostics", "unsupported diagnostics schema")
    contract_id = data.get("contract_id")
    if contract_id is not None and (
        not isinstance(contract_id, str) or _SAFE_DIAGNOSTIC_SHA.fullmatch(contract_id) is None
    ):
        raise PayloadValidationError("diagnostics contract_id", "diagnostics contract_id must be sha256 or null")
    purpose = data.get("purpose")
    if not isinstance(purpose, str) or not purpose or len(purpose) > 64:
        raise PayloadValidationError("diagnostics purpose", "diagnostics purpose must be a bounded string")
    counts = {
        field: _diagnostic_count(data, field)
        for field in ("expected_trials", "observed_trials", "scoreable_trials", "missing_trials")
    }
    if counts["scoreable_trials"] > counts["observed_trials"]:
        raise PayloadValidationError("diagnostics scoreable_trials", "scoreable trials exceed observed trials")
    return {
        "schema_version": 1,
        "contract_id": contract_id,
        "purpose": purpose,
        **counts,
        "outcome_counts": _diagnostic_count_map(data, "outcome_counts"),
        "owner_counts": _diagnostic_count_map(data, "owner_counts"),
        "timeouts_by_owner": _diagnostic_count_map(data, "timeouts_by_owner"),
        "failures": _diagnostic_failures(data.get("failures")),
        "retry_eligible": _diagnostic_boolean(data, "retry_eligible"),
        "contract_certified": _diagnostic_boolean(data, "contract_certified"),
        "artifact_references": _diagnostic_artifacts(data.get("artifact_references")),
    }


def _diagnostic_count(data: dict[str, Any], field: str) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PayloadValidationError(f"diagnostics {field}", f"diagnostics {field} must be nonnegative")
    return value


def _diagnostic_count_map(data: dict[str, Any], field: str) -> dict[str, int]:
    value = data.get(field)
    if not isinstance(value, dict):
        raise PayloadValidationError(f"diagnostics {field}", f"diagnostics {field} must be an object")
    result: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or _SAFE_DIAGNOSTIC_SLUG.fullmatch(key) is None:
            raise PayloadValidationError(f"diagnostics {field}", f"diagnostics {field} has an unsafe key")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise PayloadValidationError(f"diagnostics {field}", f"diagnostics {field} has an invalid count")
        result[key] = count
    return dict(sorted(result.items()))


def _diagnostic_failures(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) > 16:
        raise PayloadValidationError("diagnostics failures", "diagnostics failures must be a bounded list")
    failures = []
    for raw in value:
        if not isinstance(raw, dict):
            raise PayloadValidationError("diagnostics failures", "diagnostics failure must be an object")
        category, owner = raw.get("category"), raw.get("owner")
        if not all(
            isinstance(item, str) and _SAFE_DIAGNOSTIC_SLUG.fullmatch(item) is not None for item in (category, owner)
        ):
            raise PayloadValidationError("diagnostics failures", "diagnostics failure has an unsafe identity")
        count, actionable = raw.get("count"), raw.get("actionable")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1 or not isinstance(actionable, bool):
            raise PayloadValidationError("diagnostics failures", "diagnostics failure has invalid fields")
        failures.append({"category": category, "owner": owner, "count": count, "actionable": actionable})
    return failures


def _diagnostic_boolean(data: dict[str, Any], field: str) -> bool:
    value = data.get(field)
    if not isinstance(value, bool):
        raise PayloadValidationError(f"diagnostics {field}", f"diagnostics {field} must be a boolean")
    return value


def _diagnostic_artifacts(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 8:
        raise PayloadValidationError("diagnostics artifact_references", "artifact references must be bounded")
    references = []
    for raw in value:
        if not isinstance(raw, dict):
            raise PayloadValidationError("diagnostics artifact_references", "artifact reference must be an object")
        kind, path, digest = raw.get("kind"), raw.get("path"), raw.get("sha256")
        relative = PurePosixPath(path) if isinstance(path, str) else PurePosixPath("/")
        if (
            not isinstance(kind, str)
            or _SAFE_DIAGNOSTIC_SLUG.fullmatch(kind) is None
            or not isinstance(path, str)
            or relative.is_absolute()
            or "\\" in path
            or any(part in {"", ".", ".."} for part in relative.parts)
            or not isinstance(digest, str)
            or _SAFE_DIAGNOSTIC_SHA.fullmatch(digest) is None
        ):
            raise PayloadValidationError("diagnostics artifact_references", "artifact reference is unsafe")
        references.append({"kind": kind, "path": path, "sha256": digest})
    return references


def _safe_owner(owner: str) -> str:
    return owner if owner in _KNOWN_OWNERS else "unknown"


def _failure_category(trial: TrialResult, owner: str) -> str:
    if trial.failure_category and _SAFE_SLUG.fullmatch(trial.failure_category):
        return trial.failure_category
    if trial.outcome is Outcome.MISSING:
        return "missing"
    if trial.outcome is Outcome.CANDIDATE_INVALID:
        return "candidate_invalid"
    if trial.outcome is Outcome.TIMEOUT:
        return f"{owner}_timeout"
    if trial.outcome is Outcome.CANCELLED:
        return "cancelled"
    return f"{owner}_infrastructure"


def _artifact_references(record: EvaluationRecord) -> tuple[dict[str, str], ...]:
    references = []
    for kind, raw in (
        ("artifacts", record.artifacts),
        ("evaluation_contract", record.evaluation_contract),
        ("preflight_receipt", record.preflight_receipt),
        ("candidate_runtime", record.candidate_runtime),
    ):
        if not isinstance(raw, dict):
            continue
        path = raw.get("path")
        digest = raw.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            continue
        relative = PurePosixPath(path)
        if (
            relative.is_absolute()
            or "\\" in path
            or any(part in {"", ".", ".."} for part in relative.parts)
            or not _SAFE_SHA256.fullmatch(digest)
        ):
            continue
        references.append({"kind": kind, "path": path, "sha256": digest})
    return tuple(references)
