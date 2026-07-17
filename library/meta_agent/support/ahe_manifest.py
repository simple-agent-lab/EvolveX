"""Extract and validate the required AHE change manifest."""

from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any

MANIFEST_START = "<AHE_CHANGE_MANIFEST>"
MANIFEST_END = "</AHE_CHANGE_MANIFEST>"
_TOP_LEVEL = {"schema_version", "generation", "parent", "decision", "changes", "validation"}
_CHANGE_KEYS = {
    "id",
    "type",
    "files",
    "evidence_tasks",
    "root_cause",
    "targeted_fix",
    "predicted_effects",
    "risk_tasks",
    "component",
}


def extract_manifest(output: str) -> dict[str, Any]:
    starts = [match.start() for match in re.finditer(re.escape(MANIFEST_START), output)]
    ends = [match.start() for match in re.finditer(re.escape(MANIFEST_END), output)]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        raise ValueError("meta-agent output must contain exactly one AHE manifest block")
    raw = output[starts[0] + len(MANIFEST_START) : ends[0]].strip()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("AHE manifest must be a JSON object")
    return payload


def _strings(value: object, label: str, *, nonempty: bool) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} must be a list of nonempty strings")
    if nonempty and not value:
        raise ValueError(f"{label} must not be empty")
    return list(value)


def _target_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or len(path.parts) < 2 or path.parts[0] != "target":
        raise ValueError(f"unsafe AHE manifest file: {value}")
    return path.as_posix()


def validate_manifest(
    payload: dict[str, Any],
    *,
    genid: str,
    parent: str | None,
    changed_paths: list[str],
    evidence_tasks: set[str],
) -> dict[str, Any]:
    if set(payload) != _TOP_LEVEL or payload.get("schema_version") != 1:
        raise ValueError("AHE manifest must match the version-1 schema")
    if str(payload.get("generation")) != genid or str(payload.get("parent")) != str(parent):
        raise ValueError("AHE manifest identity does not match operator context")
    if payload.get("decision") not in {"keep", "revise", "rollback_pivot"}:
        raise ValueError("invalid AHE decision")
    changes = payload.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ValueError("AHE manifest changes must not be empty")
    covered: list[str] = []
    change_types: list[str] = []
    seen_ids: set[str] = set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != _CHANGE_KEYS:
            raise ValueError("AHE manifest change must match the version-1 schema")
        change_id = change.get("id")
        if not isinstance(change_id, str) or not change_id.strip() or change_id in seen_ids:
            raise ValueError("AHE manifest change ids must be unique nonempty strings")
        seen_ids.add(change_id)
        change_type = change.get("type")
        if change_type not in {"new", "improvement", "rollback"}:
            raise ValueError("invalid AHE change type")
        change_types.append(change_type)
        component = change.get("component")
        if component not in {"prompt", "tool", "control_flow", "memory", "middleware", "other"}:
            raise ValueError("invalid AHE component")
        for field in ("root_cause", "targeted_fix"):
            if not isinstance(change.get(field), str) or not change[field].strip():
                raise ValueError(f"AHE manifest {field} must not be empty")
        covered.extend(_target_path(path) for path in _strings(change.get("files"), "files", nonempty=True))
        cited = _strings(change.get("evidence_tasks"), "evidence_tasks", nonempty=True)
        predicted = _strings(change.get("predicted_effects"), "predicted_effects", nonempty=True)
        risks = _strings(change.get("risk_tasks"), "risk_tasks", nonempty=False)
        unknown = sorted((set(cited) | set(predicted) | set(risks)) - evidence_tasks)
        if unknown:
            raise ValueError("AHE manifest cites tasks without debugger evidence: " + ", ".join(unknown))
    if len(covered) != len(set(covered)) or sorted(covered) != sorted(changed_paths):
        raise ValueError("AHE manifest files must cover every changed target path exactly once")
    if payload["decision"] == "rollback_pivot" and (
        "rollback" not in change_types or not any(kind != "rollback" for kind in change_types)
    ):
        raise ValueError("rollback_pivot requires rollback and non-rollback changes")
    validation = payload.get("validation")
    if not isinstance(validation, dict) or set(validation) != {"commands", "result"}:
        raise ValueError("AHE manifest validation must match the version-1 schema")
    _strings(validation.get("commands"), "validation.commands", nonempty=True)
    if validation.get("result") != "passed":
        raise ValueError("AHE manifest validation result must be passed")
    return payload
