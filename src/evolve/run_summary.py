from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .archive import RECEIPT_CERTIFIED_FIELD, archive_path, merged_rows, verify_integrity
from .config import load_config
from .git import git
from .population import generation_number, tag_matches_candidate


def _target_reached_at(config: dict[str, Any], rows: list[dict[str, Any]]) -> int | None:
    experiment = config.get("experiment")
    target = experiment.get("target_score") if isinstance(experiment, dict) else None
    if not isinstance(target, (int, float)) or isinstance(target, bool) or not math.isfinite(float(target)):
        return None
    generations = [
        generation
        for row in rows
        if (generation := generation_number(str(row.get("genid") or ""))) is not None
        and row.get("valid_parent") is True
        and isinstance(row.get("score"), (int, float))
        and not isinstance(row.get("score"), bool)
        and float(row["score"]) >= float(target)
    ]
    return min(generations, default=None)


def _validation_rejection(workspace: Path, row: dict[str, Any], validation_enabled: bool) -> list[str]:
    genid = str(row.get("genid") or "?")
    findings: list[str] = []
    if not validation_enabled:
        findings.append(f"gen/{genid}: rejected_validation is not allowed without an operators.validate stage")
        return findings
    result_path = workspace / "runs" / f"gen-{genid}" / "validate" / "result.json"
    try:
        result = json.loads(result_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        findings.append(f"gen/{genid}: validation rejection has no readable validate/result.json ({error})")
        return findings
    if not isinstance(result, dict) or result.get("accept") is not False or not isinstance(result.get("reason"), str):
        findings.append(f"gen/{genid}: validate/result.json does not certify an explicit rejection")
    tag = git(workspace, "rev-parse", "-q", "--verify", f"refs/tags/gen/{genid}^{{commit}}", check=False)
    if tag.returncode == 0:
        findings.append(f"gen/{genid}: rejected pre-commit candidate unexpectedly has a generation tag")
    return findings


def _evaluated_generation(workspace: Path, row: dict[str, Any]) -> list[str]:
    genid = str(row.get("genid") or "?")
    findings: list[str] = []
    if row.get(RECEIPT_CERTIFIED_FIELD) is not True:
        findings.append(f"gen/{genid}: evaluation is not receipt-certified")
    if row.get("outcome") != "benchmark_complete":
        findings.append(f"gen/{genid}: expected benchmark_complete, got {row.get('outcome')!r}")
    if row.get("pending_gate_record") is not False:
        findings.append(f"gen/{genid}: gate/record did not finish")
    if row.get("valid_parent") not in {True, False} or row.get("verdict") not in {"keep", "discard"}:
        findings.append(f"gen/{genid}: gate decision is missing or invalid")
    elif (row.get("valid_parent") is True) != (row.get("verdict") == "keep"):
        findings.append(f"gen/{genid}: gate decision is contradictory")
    if not tag_matches_candidate(workspace, row, genid):
        findings.append(f"gen/{genid}: tag does not resolve to candidate_commit")
    return findings


def build_run_summary(workspace: Path, *, through: int) -> dict[str, Any]:
    """Assess whether a requested run reached recipe-valid terminal states."""
    if through < 0:
        raise ValueError("through must be non-negative")
    workspace = workspace.resolve()
    config = load_config(workspace / "evolve.yaml")
    operators = config.get("operators")
    validation_enabled = isinstance(operators, dict) and isinstance(operators.get("validate"), dict)
    rows = merged_rows(archive_path(workspace))
    findings = [f"integrity: {finding}" for finding in verify_integrity(workspace)]
    assessed: list[dict[str, Any]] = []

    rows_by_generation: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        genid = str(row.get("genid") or "")
        generation = generation_number(genid)
        if generation is not None and generation <= through:
            rows_by_generation.setdefault(generation, []).append(row)

    target_reached_at = _target_reached_at(config, rows)
    experiment = config.get("experiment")
    configured_children = experiment.get("children_per_gen", 1) if isinstance(experiment, dict) else 1
    children_per_gen = int(configured_children)
    for generation in range(through + 1):
        generation_rows = rows_by_generation.get(generation, [])
        if not generation_rows:
            if target_reached_at is None or generation <= target_reached_at:
                findings.append(f"generation {generation}: no terminal row was recorded")
            continue
        if generation > 0 and (target_reached_at is None or generation <= target_reached_at):
            expected_genids = (
                {str(generation)}
                if children_per_gen == 1
                else {f"{generation}-{child}" for child in range(children_per_gen)}
            )
            actual_genids = {str(row.get("genid") or "") for row in generation_rows}
            if actual_genids != expected_genids:
                findings.append(
                    f"generation {generation}: expected child rows {sorted(expected_genids)}, got {sorted(actual_genids)}"
                )
        for row in generation_rows:
            genid = str(row.get("genid") or "?")
            status = str(row.get("status") or "pending")
            before = len(findings)
            if status == "complete":
                findings.extend(_evaluated_generation(workspace, row))
                if generation == 0 and (row.get("valid_parent") is not True or row.get("verdict") != "keep"):
                    findings.append("gen/0: baseline must be an eligible parent")
                terminal_kind = "evaluated"
            elif status == "rejected_validation" and generation > 0:
                findings.extend(_validation_rejection(workspace, row, validation_enabled))
                terminal_kind = "validation_rejected"
            else:
                findings.append(f"gen/{genid}: terminal status {status!r} is not a successful run outcome")
                terminal_kind = "failed"
            assessed.append(
                {
                    "genid": genid,
                    "status": status,
                    "terminal_kind": terminal_kind,
                    "ok": len(findings) == before,
                }
            )

    completed = [generation for generation in rows_by_generation if generation <= through]
    components_path = workspace / ".evolve-components.json"
    try:
        components = json.loads(components_path.read_text())
    except (OSError, json.JSONDecodeError):
        components = {}
    recipe = components.get("recipe") if isinstance(components, dict) else None
    return {
        "schema_version": 1,
        "status": "passed" if not findings else "failed",
        "workspace": str(workspace),
        "recipe": recipe,
        "requested_through": through,
        "completed_through": max(completed, default=None),
        "target_reached": target_reached_at is not None,
        "target_reached_at": target_reached_at,
        "generations": assessed,
        "findings": findings,
    }


def write_run_summary(workspace: Path, *, through: int) -> tuple[dict[str, Any], Path]:
    summary = build_run_summary(workspace, through=through)
    path = workspace.resolve() / "runs" / "run-summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary, path


def assert_run_success(workspace: Path, *, through: int) -> dict[str, Any]:
    summary, path = write_run_summary(workspace, through=through)
    if summary["status"] != "passed":
        details = "; ".join(str(finding) for finding in summary["findings"][:5])
        raise RuntimeError(f"run assertion failed: {details}; summary={path}")
    return summary
