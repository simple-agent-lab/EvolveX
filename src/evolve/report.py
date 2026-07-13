from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .population import (
    SCORED_STATUSES,
    baseline_task_set_hash,
    best_row,
    looks_mechanism_written,
    rows,
)


def format_status(workspace: Path) -> str:
    workspace = workspace.resolve()
    rows_ = rows(workspace)
    best = best_row(workspace, rows_)
    lines = [
        f"rows: {len(rows_)}",
        f"best_genid: {_value(best.get('genid') if best else None)}",
        f"best_score: {_value(best.get('score') if best else None)}",
        f"budget_spent_usd: {_format_number(_budget_spent(rows_))}",
    ]
    for status, count in sorted(Counter(str(row.get("status", "pending")) for row in rows_).items()):
        lines.append(f"status.{status}: {count}")
    return "\n".join(lines) + "\n"


def format_report(workspace: Path) -> str:
    workspace = workspace.resolve()
    rows_ = rows(workspace)
    task_set_status = _task_set_hash_status(workspace, rows_)
    best = best_row(workspace, rows_) if task_set_status == "consistent" else None
    cohorts = _cohort_bests(workspace, rows_)
    anchor = _anchor_best(workspace, rows_)
    lines = [
        "Research claim checklist",
        f"rows: {len(rows_)}",
        f"best_genid: {_value(best.get('genid') if best else None)}",
        f"best_score: {_value(best.get('score') if best else None)}",
        f"task_set_hash: {task_set_status}",
        f"unstamped_rows: {_unstamped_count(workspace, rows_)}",
        f"comparison_allowed: {str(task_set_status == 'consistent').lower()}",
        f"cross_round_claim: {'anchor_only' if task_set_status != 'consistent' else 'same_hash'}",
        f"budget_spent_usd: {_format_number(_budget_spent(rows_))}",
    ]
    for task_hash, row in sorted(cohorts.items()):
        lines.append(f"cohort.{task_hash}.best_genid: {row['genid']}")
        lines.append(f"cohort.{task_hash}.best_score: {_value(row['score'])}")
    if anchor is not None:
        lines.append(f"anchor.best_genid: {anchor['genid']}")
        lines.append(f"anchor.best_score: {_value(anchor['score'])}")
    return "\n".join(lines) + "\n"


def _task_set_hash_status(workspace: Path, rows: list[dict[str, Any]]) -> str:
    hashes = {
        str(evaluation["task_set_hash"])
        for evaluation in _claim_evaluations(workspace, rows)
        if evaluation.get("kind") != "anchor"
    }
    if len(hashes) <= 1:
        return "consistent"
    return "mismatch"


def _cohort_bests(workspace: Path, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    bests: dict[str, dict[str, Any]] = {}
    for evaluation in _claim_evaluations(workspace, rows):
        if evaluation.get("kind") == "anchor":
            continue
        task_hash = str(evaluation["task_set_hash"])
        current = bests.get(task_hash)
        if current is None or float(evaluation["score"]) > float(current["score"]):
            bests[task_hash] = evaluation
    return bests


def _anchor_best(workspace: Path, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for evaluation in _claim_evaluations(workspace, rows):
        if evaluation.get("kind") != "anchor":
            continue
        if best is None or float(evaluation["score"]) > float(best["score"]):
            best = evaluation
    return best


def _claim_evaluations(workspace: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for row in rows:
        if not _looks_mechanism_written(workspace, row):
            continue
        if row.get("valid_parent") is not True:
            continue
        _append_claim_evaluation(evaluations, row, row)
        for entry in row.get("evals", []) or []:
            if isinstance(entry, dict) and _entry_looks_mechanism_written(row, entry):
                _append_claim_evaluation(evaluations, row, entry)
    return evaluations


def _entry_looks_mechanism_written(row: dict[str, Any], entry: dict[str, Any]) -> bool:
    if entry.get("tag") != row.get("tag"):
        return False
    if entry.get("valid_parent") is not True:
        return False
    if entry.get("status") not in SCORED_STATUSES:
        return False
    if entry.get("task_set_hash") is None or not (entry.get("evaluator_fingerprint") or entry.get("evaluator_tree")):
        return False
    cost = entry.get("cost")
    if not isinstance(cost, dict):
        return False
    return _is_number(entry.get("score"))


def _append_claim_evaluation(evaluations: list[dict[str, Any]], row: dict[str, Any], source: dict[str, Any]) -> None:
    if source.get("status") not in SCORED_STATUSES:
        return
    if source.get("task_set_hash") is None or not _is_number(source.get("score")):
        return
    evaluations.append(
        {
            "genid": row.get("genid"),
            "score": source.get("score"),
            "task_set_hash": source.get("task_set_hash"),
            "kind": source.get("kind", "eval"),
        }
    )


def _unstamped_count(workspace: Path, rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if not _looks_mechanism_written(workspace, row))


def _looks_mechanism_written(workspace: Path, row: dict[str, Any]) -> bool:
    return looks_mechanism_written(workspace, row)


def _is_claim_candidate(workspace: Path, row: dict[str, Any], comparison_hash: str | None) -> bool:
    return (
        comparison_hash is not None
        and _looks_mechanism_written(workspace, row)
        and row.get("valid_parent") is True
        and row.get("status") in SCORED_STATUSES
        and row.get("task_set_hash") == comparison_hash
        and _is_number(row.get("score"))
    )


def _baseline_task_set_hash(workspace: Path, rows: list[dict[str, Any]]) -> str | None:
    return baseline_task_set_hash(workspace, rows)


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
    return isinstance(value, int | float) and not isinstance(value, bool)
