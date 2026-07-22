from __future__ import annotations

from pathlib import Path
from typing import Any

from .archive import RECEIPT_CERTIFIED_FIELD
from .evaluation.identity import fixed_evaluation_identity
from .git import tag_exists


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
    from .frozen.interfaces import ArchiveView

    return ArchiveView(workspace.resolve()).rows()


def baseline_task_set_hash(workspace: Path, rows_: list[dict[str, Any]] | None = None) -> str | None:
    del rows_
    expected = fixed_evaluation_identity(workspace.resolve())
    return expected["task_set_hash"] if expected is not None else None


def looks_mechanism_written(workspace: Path, row: dict[str, Any]) -> bool:
    genid = str(row.get("genid", ""))
    evaluations = [row]
    if isinstance(row.get("evals"), list):
        evaluations.extend(row["evals"])
    return tag_exists(workspace, f"gen/{genid}") and any(
        isinstance(entry, dict) and entry.get(RECEIPT_CERTIFIED_FIELD) is True and entry.get("tag") == f"gen/{genid}"
        for entry in evaluations
    )


def valid_parent_rows(workspace: Path, rows_: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    from .frozen.interfaces import ArchiveView

    view = ArchiveView(workspace.resolve())
    if rows_ is None:
        return view.valid_parents()
    expected = fixed_evaluation_identity(view.workspace)
    if expected is None:
        return []
    return [row for row in rows_ if is_parent_record(row, expected)]


def best_row(workspace: Path, rows_: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    candidates = valid_parent_rows(workspace, rows_)
    return max(candidates, key=lambda row: float(row["score"]), default=None)


def is_parent_record(row: dict[str, Any], expected: dict[str, str]) -> bool:
    return (
        row.get("outcome") == "benchmark_complete"
        and row.get("purpose") in {"candidate", "genesis"}
        and row.get("selection_eligible") is True
        and row.get("pending_gate_record") is False
        and row.get("valid_parent") is True
        and row.get(RECEIPT_CERTIFIED_FIELD) is True
        and all(row.get(field) == value for field, value in expected.items())
        and isinstance(row.get("score"), (int, float))
        and not isinstance(row.get("score"), bool)
    )
