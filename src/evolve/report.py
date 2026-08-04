from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

from .archive import RECEIPT_CERTIFIED_FIELD
from .frozen.interfaces import ArchiveView
from .population import fixed_evaluation_identity, is_parent_record, looks_mechanism_written, tag_matches_candidate


def format_status(workspace: Path) -> str:
    view = ArchiveView(workspace.resolve())
    rows = view.rows()
    best = view.best_ever()
    lines = [
        f"rows: {len(rows)}",
        f"best_genid: {_value(best.get('genid') if best else None)}",
        f"best_score: {_value(best.get('score') if best else None)}",
        f"budget_spent_usd: {_format_number(_budget_spent(rows))}",
    ]
    for status, count in sorted(Counter(str(row.get("status", "pending")) for row in rows).items()):
        lines.append(f"status.{status}: {count}")
    if rows:
        latest = max(rows, key=lambda row: _generation_key(row.get("genid")))
        lines.append(f"latest.genid: {_value(latest.get('genid'))}")
        lines.append(f"latest.status: {_value(latest.get('status'))}")
        if latest.get("failure_stage"):
            lines.append(f"latest.failure_stage: {_value(latest.get('failure_stage'))}")
    return "\n".join(lines) + "\n"


def _generation_key(value: object) -> tuple[int, int | str]:
    text = str(value or "")
    return (1, int(text)) if text.isdigit() else (0, text)


def format_report(workspace: Path) -> str:
    view = ArchiveView(workspace.resolve())
    rows = view.rows()
    expected = fixed_evaluation_identity(view.workspace)
    parents = [] if expected is None else [row for row in rows if is_parent_record(row, expected, view.workspace)]
    claims = _claim_evaluations(view.workspace, rows, parents, expected)
    task_set_status = "unverifiable" if expected is None else _task_set_hash_status(claims)
    best = max(parents, key=lambda row: float(row["score"]), default=None) if task_set_status == "consistent" else None
    cohorts = _cohort_bests(claims)
    anchor = _anchor_best(claims)
    lines = [
        "Research claim checklist",
        f"rows: {len(rows)}",
        f"best_genid: {_value(best.get('genid') if best else None)}",
        f"best_score: {_value(best.get('score') if best else None)}",
        f"task_set_hash: {task_set_status}",
        f"evaluation_identity: {'verified' if expected is not None else 'unverifiable'}",
        f"migration_required: {str(expected is None).lower()}",
        f"unstamped_rows: {_unstamped_count(view.workspace, rows)}",
        f"comparison_allowed: {str(task_set_status == 'consistent').lower()}",
        f"cross_round_claim: {'same_hash' if task_set_status == 'consistent' else 'unavailable'}",
        f"budget_spent_usd: {_format_number(_budget_spent(rows))}",
    ]
    for task_hash, row in sorted(cohorts.items()):
        lines.append(f"cohort.{task_hash}.best_genid: {row['genid']}")
        lines.append(f"cohort.{task_hash}.best_score: {_value(row['score'])}")
    if anchor is not None:
        lines.append(f"anchor.best_genid: {anchor['genid']}")
        lines.append(f"anchor.best_score: {_value(anchor['score'])}")
    return "\n".join(lines) + "\n"


def _task_set_hash_status(claims: list[dict[str, Any]]) -> str:
    hashes = {str(evaluation["task_set_hash"]) for evaluation in claims if evaluation.get("kind") != "anchor"}
    return "consistent" if len(hashes) <= 1 else "mismatch"


def _cohort_bests(claims: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    bests: dict[str, dict[str, Any]] = {}
    for evaluation in claims:
        if evaluation.get("kind") == "anchor":
            continue
        task_hash = str(evaluation["task_set_hash"])
        current = bests.get(task_hash)
        if current is None or float(evaluation["score"]) > float(current["score"]):
            bests[task_hash] = evaluation
    return bests


def _anchor_best(claims: list[dict[str, Any]]) -> dict[str, Any] | None:
    anchors = [evaluation for evaluation in claims if evaluation.get("kind") == "anchor"]
    return max(anchors, key=lambda evaluation: float(evaluation["score"]), default=None)


def _claim_evaluations(
    workspace: Path,
    rows: list[dict[str, Any]],
    parents: list[dict[str, Any]],
    expected: dict[str, str] | None,
) -> list[dict[str, Any]]:
    evaluations = [
        {
            "genid": row.get("genid"),
            "score": row["score"],
            "task_set_hash": row["task_set_hash"],
            "kind": "eval",
        }
        for row in parents
    ]
    for row in rows:
        for entry in row.get("evals", []) or []:
            if isinstance(entry, dict) and _reportable_anchor(workspace, row, entry, expected):
                evaluations.append(
                    {
                        "genid": row.get("genid"),
                        "score": entry["score"],
                        "task_set_hash": entry["task_set_hash"],
                        "kind": "anchor",
                    }
                )
    return evaluations


def _reportable_anchor(
    workspace: Path, row: dict[str, Any], entry: dict[str, Any], expected: dict[str, str] | None
) -> bool:
    genid = str(row.get("genid", ""))
    return (
        expected is not None
        and entry.get(RECEIPT_CERTIFIED_FIELD) is True
        and entry.get("kind") == "anchor"
        and entry.get("outcome") == "benchmark_complete"
        and entry.get("purpose") == "anchor"
        and entry.get("evaluator_fingerprint") == expected["evaluator_fingerprint"]
        and entry.get("runtime_fingerprint") == expected["runtime_fingerprint"]
        and tag_matches_candidate(workspace, entry, genid)
        and _is_number(entry.get("score"))
        and isinstance(entry.get("task_set_hash"), str)
    )


def _unstamped_count(workspace: Path, rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if not looks_mechanism_written(workspace, row))


def _budget_spent(rows: list[dict[str, Any]]) -> float:
    total = 0.0
    for row in rows:
        cost = row.get("cost")
        if isinstance(cost, dict) and _is_number(cost.get("usd")):
            total += float(cost["usd"])
    return total


def _value(value: Any) -> str:
    if value is None:
        return "none"
    if _is_number(value):
        return _format_number(float(value))
    return str(value)


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return f"{value:.1f}"
    return str(value)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(float(value))
