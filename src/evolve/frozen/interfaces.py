from __future__ import annotations

import math
import random
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from ..archive import archive_path, ensure_local_archive, merged_rows
from ..population import fixed_evaluation_identity, is_parent_record

PROTOCOL_VERSION = 1
Row = dict[str, Any]
_SAFE_DIAGNOSTIC_SLUG = re.compile(r"[a-z0-9_]{1,64}")
_SAFE_DIAGNOSTIC_SHA = re.compile(r"[a-f0-9]{64}")


class PayloadValidationError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(message)


@dataclass(frozen=True)
class OperatorContext:
    workspace: Path
    checkout: Path
    run_dir: Path
    genid: str
    parent: str | None
    round: int | None
    fan_out: int
    config: dict[str, Any]
    rng: random.Random


@dataclass(frozen=True)
class ArchiveView:
    workspace: Path

    def rows(self) -> list[Row]:
        from ..config import experiment_id

        workspace = self.workspace.resolve()
        ensure_local_archive(workspace, experiment_id(workspace))
        return merged_rows(archive_path(workspace))

    def valid_parents(self) -> list[Row]:
        expected = fixed_evaluation_identity(self.workspace)
        if expected is None:
            return []
        return [row for row in self.rows() if is_parent_record(row, expected, self.workspace)]

    def best_ever(self) -> Row | None:
        candidates = [
            row
            for row in self.valid_parents()
            if isinstance(row.get("score"), (int, float)) and not isinstance(row.get("score"), bool)
        ]
        return max(candidates, key=lambda row: float(row["score"]), default=None)

    def row(self, genid: str) -> Row | None:
        for candidate in self.rows():
            if str(candidate.get("genid")) == str(genid):
                return candidate
        return None

    def matched_parent(self, child: Row | None, parent_id: str) -> bool:
        return child is not None and str(child.get("parent")) == str(parent_id)


class SelectOperator(ABC):
    @abstractmethod
    def pick(self, archive: ArchiveView, ctx) -> SelectResult: ...


class RolloutOperator(ABC):
    @abstractmethod
    def rollout(self, checkout: Path, ctx) -> RolloutResult: ...


class TraceAnalyzerOperator(ABC):
    @abstractmethod
    def analyze(self, checkout: Path, ctx) -> TraceAnalyzerResult: ...


class MetaAgentOperator(ABC):
    @abstractmethod
    def run(self, checkout: Path, observation: str, ctx) -> MetaAgentResult: ...


class ValidateOperator(ABC):
    @abstractmethod
    def validate(self, checkout: Path, ctx) -> ValidateResult: ...


class NoveltyOperator(ABC):
    @abstractmethod
    def assess(self, checkout: Path, ctx) -> NoveltyResult: ...


class GateOperator(ABC):
    @abstractmethod
    def decide(self, child: Row, parent: Row | None, ctx) -> GateResult: ...


class RecordOperator(ABC):
    @abstractmethod
    def annotate(self, child: Row, ctx) -> RecordResult: ...


class ReflectOperator(ABC):
    @abstractmethod
    def reflect(self, archive, ctx) -> ReflectResult: ...


@dataclass(frozen=True)
class SelectResult:
    parents: list[str]


@dataclass(frozen=True)
class RolloutResult:
    summary: dict[str, Any]
    artifacts: list[str]


@dataclass(frozen=True)
class TraceAnalyzerResult:
    summary: dict[str, Any]
    artifacts: list[str]


@dataclass(frozen=True)
class MetaAgentResult:
    changed: list[str]
    notes: list[str]
    usage: dict[str, Any]


@dataclass(frozen=True)
class ValidateResult:
    accept: bool
    reason: str
    artifacts: list[str]


@dataclass(frozen=True)
class NoveltyResult:
    novelty: float  # 1.0 = wholly novel, 0.0 = an exact duplicate of a prior diff
    accept: bool  # reject near-duplicate candidate edits before they are evaluated


@dataclass(frozen=True)
class GateResult:
    decision: Literal["accept", "reject"]
    reason: str


@dataclass(frozen=True)
class RecordResult:
    fields: dict[str, Any]


@dataclass(frozen=True)
class ReflectResult:
    ops: list  # playbook delta operations (full-state entries), never a rewrite


def validate_select_payload(payload: SelectResult | dict[str, Any]) -> dict[str, Any]:
    data = _payload_dict(payload)
    parents = data.get("parents")
    if not isinstance(parents, list) or not parents or not all(str(parent) for parent in parents):
        raise PayloadValidationError("parents", "parents must be a non-empty list")
    return {"parents": [str(parent) for parent in parents]}


def validate_rollout_payload(payload: RolloutResult | dict[str, Any]) -> dict[str, Any]:
    data = _payload_dict(payload)
    _require_type(data, "summary", dict, "summary must be a dict")
    _require_type(data, "artifacts", list, "artifacts must be a list")
    return {"summary": data["summary"], "artifacts": [str(artifact) for artifact in data["artifacts"]]}


def validate_trace_analyzer_payload(payload: TraceAnalyzerResult | dict[str, Any]) -> dict[str, Any]:
    data = _payload_dict(payload)
    _require_type(data, "summary", dict, "summary must be a dict")
    _require_type(data, "artifacts", list, "artifacts must be a list")
    return {"summary": data["summary"], "artifacts": [str(artifact) for artifact in data["artifacts"]]}


def validate_meta_agent_payload(payload: MetaAgentResult | dict[str, Any]) -> dict[str, Any]:
    data = _payload_dict(payload)
    _require_type(data, "changed", list, "changed must be a list")
    _require_type(data, "notes", list, "notes must be a list")
    _require_type(data, "usage", dict, "usage must be a dict")
    usage = validate_meta_agent_usage_payload(data["usage"])
    return {
        "changed": [str(path) for path in data["changed"]],
        "notes": [str(note) for note in data["notes"]],
        "usage": usage,
    }


def validate_validate_payload(payload: ValidateResult | dict[str, Any]) -> dict[str, Any]:
    data = _payload_dict(payload)
    _require_type(data, "accept", bool, "accept must be a boolean")
    _require_type(data, "reason", str, "reason must be a string")
    _require_type(data, "artifacts", list, "artifacts must be a list")
    return {"accept": data["accept"], "reason": data["reason"], "artifacts": [str(p) for p in data["artifacts"]]}


def validate_gate_payload(payload: GateResult | dict[str, Any]) -> dict[str, Any]:
    data = _payload_dict(payload)
    if data.get("decision") not in {"accept", "reject"}:
        raise PayloadValidationError("decision", "decision must be accept or reject")
    _require_type(data, "reason", str, "reason must be a string")
    return {"decision": data["decision"], "reason": data["reason"]}


def validate_novelty_payload(payload: NoveltyResult | dict[str, Any]) -> dict[str, Any]:
    data = _payload_dict(payload)
    novelty = data.get("novelty")
    if not isinstance(novelty, (int, float)) or isinstance(novelty, bool) or not math.isfinite(float(novelty)):
        raise PayloadValidationError("novelty", "novelty must be a finite number")
    _require_type(data, "accept", bool, "accept must be a boolean")
    return {"novelty": float(novelty), "accept": data["accept"]}


def validate_record_payload(payload: RecordResult | dict[str, Any]) -> dict[str, Any]:
    data = _payload_dict(payload)
    _require_type(data, "fields", dict, "fields must be a dict")
    return {"fields": data["fields"]}


def validate_reflect_payload(payload: ReflectResult | dict[str, Any]) -> dict[str, Any]:
    data = _payload_dict(payload)
    ops = data.get("ops")
    if not isinstance(ops, list) or not all(isinstance(op, dict) and op.get("id") for op in ops):
        raise PayloadValidationError("ops", "ops must be a list of dicts each with an id")
    return {"ops": ops}


def validate_rollout_summary_payload(payload: object) -> dict[str, Any]:
    return dict(_json_object(payload, "summary", "summary must be a JSON object"))


def validate_rollout_artifacts_payload(payload: object) -> list[str]:
    if not isinstance(payload, list):
        raise PayloadValidationError("artifacts", "artifacts must be a list")
    return [str(item) for item in payload]


def validate_meta_agent_usage_payload(payload: object) -> dict[str, Any]:
    data = _json_object(payload, "usage", "usage must be a JSON object")
    usd = data.get("usd")
    if usd is not None and (
        not isinstance(usd, (int, float)) or isinstance(usd, bool) or not math.isfinite(float(usd))
    ):
        raise PayloadValidationError("usd", "usd must be a finite number")
    return dict(data)


def validate_gate_file_payload(payload: object) -> dict[str, Any]:
    data = _json_object(payload, "valid_parent", "gate payload must be a JSON object")
    _require_type(data, "valid_parent", bool, "valid_parent must be a boolean")
    if data.get("verdict") not in {"keep", "discard"}:
        raise PayloadValidationError("verdict", "verdict must be keep or discard")
    if data["valid_parent"] is not (data["verdict"] == "keep"):
        raise PayloadValidationError("valid_parent", "valid_parent must agree with verdict")
    _require_type(data, "reason", str, "reason must be a string")
    return {
        "valid_parent": data["valid_parent"],
        "verdict": data["verdict"],
        "reason": data["reason"],
    }


def validate_novelty_file_payload(payload: object) -> dict[str, Any]:
    return validate_novelty_payload(_json_object(payload, "novelty", "novelty payload must be a JSON object"))


def validate_validate_file_payload(payload: object) -> dict[str, Any]:
    return validate_validate_payload(_json_object(payload, "accept", "validate payload must be a JSON object"))


def validate_record_fields_payload(payload: object) -> dict[str, Any]:
    return dict(_json_object(payload, "fields", "fields must be a JSON object"))


def validate_evaluation_diagnostics_payload(payload: object) -> dict[str, Any]:
    data = _json_object(payload, "diagnostics", "diagnostics must be a JSON object")
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
    normalized = {
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
    return normalized


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
        count = raw.get("count")
        actionable = raw.get("actionable")
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


def _payload_dict(payload: object) -> dict[str, Any]:
    if is_dataclass(payload) and not isinstance(payload, type):
        return asdict(payload)
    if isinstance(payload, dict):
        return dict(cast("dict[str, Any]", payload))
    raise PayloadValidationError("payload", "payload must be a dataclass result or dict")


def _require_type(data: dict[str, Any], field: str, expected: type, message: str) -> None:
    if not isinstance(data.get(field), expected):
        raise PayloadValidationError(field, message)


def _json_object(payload: object, field: str, message: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PayloadValidationError(field, message)
    return cast("dict[str, Any]", payload)


# ---------------------------------------------------------------------------
# The operator registry — the single source of truth for the operator set.
# Adding an operator is ONE entry here; the kind lists in config.py and the
# contract tests derive from it, so they can't drift (mechanism 6, DESIGN §6).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OperatorSpec:
    kind: str
    abc: type
    result: type
    method: str
    required: bool  # required: always in the loop; optional: opt-in per recipe


OPERATORS: tuple[OperatorSpec, ...] = (
    OperatorSpec("select", SelectOperator, SelectResult, "pick", True),
    OperatorSpec("rollout", RolloutOperator, RolloutResult, "rollout", True),
    OperatorSpec("trace_analyzer", TraceAnalyzerOperator, TraceAnalyzerResult, "analyze", False),
    OperatorSpec("meta_agent", MetaAgentOperator, MetaAgentResult, "run", True),
    OperatorSpec("validate", ValidateOperator, ValidateResult, "validate", False),
    OperatorSpec("novelty", NoveltyOperator, NoveltyResult, "assess", False),
    OperatorSpec("gate", GateOperator, GateResult, "decide", True),
    OperatorSpec("record", RecordOperator, RecordResult, "annotate", True),
    OperatorSpec("reflect", ReflectOperator, ReflectResult, "reflect", False),
)
OPERATOR_BY_KIND: dict[str, OperatorSpec] = {spec.kind: spec for spec in OPERATORS}
REQUIRED_OPERATOR_KINDS: tuple[str, ...] = tuple(s.kind for s in OPERATORS if s.required)
OPTIONAL_OPERATOR_KINDS: tuple[str, ...] = tuple(s.kind for s in OPERATORS if not s.required)
