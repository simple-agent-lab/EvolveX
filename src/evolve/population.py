from __future__ import annotations

from pathlib import Path
from typing import Any

from .archive import archive_path, ensure_local_archive, merged_rows
from .config import evaluator_sampling, experiment_id
from .git import tag_exists

SCORED_STATUSES = {"complete", "partial"}
KNOWN_TERMINAL_STATUSES = {
    "complete",
    "partial",
    "infra_failed",
    "invalid_proposal",
    "no_proposal",
    "operator_failed",
}


def valid_genid(genid: str) -> bool:
    return generation_number(genid) is not None


def format_genid(generation: int, child_index: int, children_per_gen: int) -> str:
    return str(generation) if children_per_gen == 1 else f"{generation}-{child_index}"


def generation_number(genid: str) -> int | None:
    if genid.isdigit():
        return int(genid)
    parts = genid.split("-", 1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[0])


def rows(workspace: Path) -> list[dict[str, Any]]:
    workspace = workspace.resolve()
    ensure_local_archive(workspace, experiment_id(workspace))
    return merged_rows(archive_path(workspace))


def baseline_task_set_hash(workspace: Path, rows_: list[dict[str, Any]] | None = None) -> str | None:
    workspace = workspace.resolve()
    candidates = rows_ if rows_ is not None else rows(workspace)
    for row in candidates:
        if str(row.get("genid")) == "0" and looks_mechanism_written(workspace, row):
            value = row.get("task_set_hash")
            return str(value) if value is not None else None
    for row in candidates:
        if looks_mechanism_written(workspace, row) and row.get("status") in SCORED_STATUSES:
            value = row.get("task_set_hash")
            return str(value) if value is not None else None
    return None


def looks_mechanism_written(workspace: Path, row: dict[str, Any]) -> bool:
    if "genid" not in row or "tag" not in row:
        return False
    genid = str(row["genid"])
    tag = str(row["tag"])
    if tag != f"gen/{genid}" or not tag_exists(workspace, tag):
        return False
    status = row.get("status")
    if status is None:
        return isinstance(row.get("mutated"), list) and isinstance(row.get("surface_violations"), list)
    if status not in KNOWN_TERMINAL_STATUSES:
        return False
    if "cost" not in row or "valid_parent" not in row:
        return False
    if status in SCORED_STATUSES:
        return row.get("task_set_hash") is not None and row.get("evaluator_tree") is not None
    return True


def valid_parent_rows(workspace: Path, rows_: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    workspace = workspace.resolve()
    candidates = rows_ if rows_ is not None else rows(workspace)
    per_round = evaluator_sampling(workspace) == "per_round"
    comparison_hash = None if per_round else baseline_task_set_hash(workspace, candidates)
    valid: list[dict[str, Any]] = []
    for row in candidates:
        if comparison_hash is None and not per_round:
            continue
        if not looks_mechanism_written(workspace, row):
            continue
        if row.get("valid_parent") is not True or row.get("status") not in SCORED_STATUSES:
            continue
        if comparison_hash is not None and row.get("task_set_hash") != comparison_hash:
            continue
        score = row.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            continue
        valid.append(row)
    return valid


def certified_parent_rows(workspace: Path, *, epoch: int) -> list[dict[str, Any]]:
    return [
        row
        for row in rows(workspace)
        if row.get("selection_eligible") is True
        and row.get("valid_parent") is True
        and row.get("epoch") == epoch
        and isinstance(row.get("score"), (int, float))
        and not isinstance(row.get("score"), bool)
    ]


def best_row(workspace: Path, rows_: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    if evaluator_sampling(workspace) == "per_round":
        return None
    best: dict[str, Any] | None = None
    best_score = float("-inf")
    for row in valid_parent_rows(workspace, rows_):
        numeric_score = float(row["score"])
        if best is None or numeric_score > best_score:
            best = row
            best_score = numeric_score
    return best
