"""Pure policy helpers for attribution-driven harness evolution."""

from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import Any

from evolve.task_vectors import normalize_task_vector

STATE_RANK = {"fail": 0, "partial": 1, "pass": 2}
_DECISIONS = {"keep", "revise", "rollback_pivot"}
_CHANGE_TYPES = {"new", "improvement", "rollback"}
_COMPONENT_LEVELS = {"prompt", "tool", "model_adapter", "environment", "control_flow"}


def _state(trials: list[dict[str, Any]], required_trials: int) -> str:
    if len(trials) != required_trials or any(item["status"] != "complete" for item in trials):
        return "unknown"
    passed = sum(float(item["reward"]) > 0 for item in trials)
    return "pass" if passed == required_trials else "fail" if passed == 0 else "partial"


def task_states(vector: object, required_trials: int = 2) -> dict[str, str]:
    """Classify each task conservatively from its complete trial outcomes."""
    if required_trials < 1:
        raise ValueError("required_trials must be positive")
    tasks = normalize_task_vector(vector)["tasks"]
    return {task_id: _state(task["trials"], required_trials) for task_id, task in tasks.items()}


def compare_states(previous: dict[str, str], current: dict[str, str]) -> dict[str, list[str]]:
    """Compare reliable task-state transitions in deterministic task-id order."""
    result = {"improved": [], "regressed": [], "unchanged": [], "unknown": []}
    for task_id in sorted(set(previous) | set(current)):
        before, after = previous.get(task_id, "unknown"), current.get(task_id, "unknown")
        if before not in STATE_RANK or after not in STATE_RANK:
            result["unknown"].append(task_id)
        elif STATE_RANK[after] > STATE_RANK[before]:
            result["improved"].append(task_id)
        elif STATE_RANK[after] < STATE_RANK[before]:
            result["regressed"].append(task_id)
        else:
            result["unchanged"].append(task_id)
    return result


def evaluate_manifest(manifest: dict[str, Any], previous: object, current: object) -> dict[str, Any]:
    """Attribute outcome changes to each manifest entry without scoring a candidate."""
    previous_states = task_states(previous)
    current_states = task_states(current)
    comparison = compare_states(previous_states, current_states)
    regressed = set(comparison["regressed"])
    changes: list[dict[str, Any]] = []
    for raw_change in manifest.get("changes", []):
        if not isinstance(raw_change, dict):
            raise ValueError("manifest changes must be objects")
        change = dict(raw_change)
        predicted_fixes = _task_list(change.get("predicted_fixes"), "predicted_fixes")
        risk_tasks = _task_list(change.get("risk_tasks"), "risk_tasks")
        verified_fixes = [task_id for task_id in predicted_fixes if current_states.get(task_id) == "pass"]
        still_failing = [task_id for task_id in predicted_fixes if task_id not in verified_fixes]
        realized_risks = [task_id for task_id in risk_tasks if task_id in regressed]
        unexpected_regressions = sorted(regressed - set(risk_tasks))
        if realized_risks and not verified_fixes:
            verdict = "HARMFUL"
        elif realized_risks:
            verdict = "MIXED"
        elif verified_fixes and len(verified_fixes) == len(predicted_fixes):
            verdict = "EFFECTIVE"
        elif verified_fixes:
            verdict = "PARTIALLY_EFFECTIVE"
        else:
            verdict = "INEFFECTIVE"
        changes.append(
            {
                **change,
                "verified_fixes": verified_fixes,
                "still_failing_predictions": still_failing,
                "realized_risks": realized_risks,
                "unexpected_regressions": unexpected_regressions,
                "verdict": verdict,
            }
        )
    return {**manifest, "changes": changes}


def select_debugger_tasks(
    current_states: dict[str, str],
    comparison: dict[str, list[str]],
    predicted_risks: list[str],
    *,
    successful_controls: int,
    seed: int,
    generation: int,
) -> dict[str, list[str]]:
    """Choose all diagnostic tasks and a deterministic rotating pass-control sample."""
    if successful_controls < 0:
        raise ValueError("successful_controls must be non-negative")
    successes = sorted(task_id for task_id, state in current_states.items() if state == "pass")
    controls = random.Random(seed + generation).sample(successes, min(successful_controls, len(successes)))
    return {
        "failure": sorted(task_id for task_id, state in current_states.items() if state == "fail"),
        "regression": sorted(set(comparison.get("regressed", []))),
        "risk": sorted(set(predicted_risks)),
        "control": controls,
    }


def validate_change_manifest(
    manifest: object,
    *,
    generation: str,
    parent: str,
    changed_paths: list[str],
    run_dir: Path,
    surface_report: dict[str, Any],
) -> dict[str, Any]:
    """Require a complete, evidence-backed manifest for an approved source edit."""
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    if str(manifest.get("generation")) != generation:
        raise ValueError("manifest generation does not match")
    if str(manifest.get("parent")) != parent:
        raise ValueError("manifest parent does not match")
    if manifest.get("decision") not in _DECISIONS:
        raise ValueError("manifest decision is invalid")
    validation = manifest.get("validation")
    if (
        not isinstance(validation, dict)
        or validation.get("status") != "passed"
        or not isinstance(validation.get("commands"), list)
    ):
        raise ValueError("manifest validation must record passed commands")

    expected_paths = _path_set(changed_paths, "changed paths")
    if not surface_report.get("ok"):
        raise ValueError("surface report is not valid")
    if _path_set(surface_report.get("mutated"), "surface mutated paths") != expected_paths:
        raise ValueError("surface paths do not match changed paths")

    changes = manifest.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ValueError("manifest changes must be a non-empty list")
    covered: list[str] = []
    for change in changes:
        _validate_change(change, run_dir)
        assert isinstance(change, dict)
        covered.extend(change["files"])
    if len(covered) != len(set(covered)):
        raise ValueError("each changed path must appear exactly once")
    if set(covered) != expected_paths:
        raise ValueError("manifest files must cover changed paths exactly")
    return dict(manifest)


def verify_relative_hash(workspace: Path, reference: object) -> Path:
    """Resolve and hash-check a workspace-relative artifact reference."""
    if not isinstance(reference, dict):
        raise ValueError("artifact reference must be an object")
    relative = reference.get("path")
    expected_hash = reference.get("sha256")
    path = _safe_path(relative, "artifact path")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError("artifact sha256 is invalid")
    resolved_workspace = workspace.resolve()
    candidate = (resolved_workspace / path).resolve()
    try:
        candidate.relative_to(resolved_workspace)
    except ValueError as error:
        raise ValueError("unsafe path") from error
    if not candidate.is_file():
        raise ValueError("artifact path does not exist")
    actual_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError("artifact sha256 does not match")
    return candidate


def _validate_change(change: object, run_dir: Path) -> None:
    if not isinstance(change, dict):
        raise ValueError("manifest change must be an object")
    if not isinstance(change.get("id"), str) or not change["id"]:
        raise ValueError("manifest change id is required")
    if change.get("type") not in _CHANGE_TYPES:
        raise ValueError("manifest change type is invalid")
    files = change.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("manifest files must cover changed paths exactly")
    for path in files:
        _safe_path(path, "manifest file")
    evidence = change.get("failure_evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("failure_evidence is required")
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("task_id"), str) or not item["task_id"]:
            raise ValueError("failure_evidence task_id is required")
        report = _safe_path(item.get("report"), "evidence report")
        report_path = (run_dir.resolve() / report).resolve()
        try:
            report_path.relative_to(run_dir.resolve())
        except ValueError as error:
            raise ValueError("unsafe path") from error
        if not report_path.is_file():
            raise ValueError("evidence report does not exist")
    for field in ("root_cause", "targeted_fix"):
        if not isinstance(change.get(field), str) or not change[field]:
            raise ValueError(f"{field} is required")
    _task_list(change.get("predicted_fixes"), "predicted_fixes", require_nonempty=True)
    _task_list(change.get("risk_tasks"), "risk_tasks")
    if change.get("component_level") not in _COMPONENT_LEVELS:
        raise ValueError("component_level is invalid")


def _task_list(value: object, field: str, *, require_nonempty: bool = False) -> list[str]:
    if (
        not isinstance(value, list)
        or (require_nonempty and not value)
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ValueError(f"{field} must be a list of task ids")
    return list(value)


def _path_set(value: object, field: str) -> set[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    paths = [_safe_path(item, field).as_posix() for item in value]
    if len(paths) != len(set(paths)):
        raise ValueError(f"{field} must not contain duplicates")
    return set(paths)


def _safe_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{field} has an unsafe path")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("unsafe path")
    return path
