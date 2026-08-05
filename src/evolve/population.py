from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .archive import RECEIPT_CERTIFIED_FIELD
from .evaluation.identity import fixed_evaluation_identity
from .git import git


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
    return any(
        isinstance(entry, dict)
        and entry.get(RECEIPT_CERTIFIED_FIELD) is True
        and tag_matches_candidate(workspace, entry, genid)
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
    return [row for row in rows_ if is_parent_record(row, expected, view.workspace)]


def best_row(workspace: Path, rows_: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    candidates = valid_parent_rows(workspace, rows_)
    return max(candidates, key=lambda row: float(row["score"]), default=None)


def tag_matches_candidate(workspace: Path, row: dict[str, Any], genid: str | None = None) -> bool:
    generation = str(row.get("genid", "")) if genid is None else str(genid)
    tag = f"gen/{generation}"
    candidate_commit = row.get("candidate_commit")
    if row.get("tag") != tag or not isinstance(candidate_commit, str) or not candidate_commit:
        return False
    resolved = git(workspace, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}", check=False)
    return resolved.returncode == 0 and resolved.stdout.strip() == candidate_commit


def is_parent_record(row: dict[str, Any], expected: dict[str, str], workspace: Path | None = None) -> bool:
    score = row.get("score")
    return (
        workspace is not None
        and row.get("outcome") == "benchmark_complete"
        and row.get("purpose") in {"candidate", "genesis"}
        and row.get("selection_eligible") is True
        and row.get("pending_gate_record") is False
        and row.get("valid_parent") is True
        and row.get("verdict") == "keep"
        and row.get(RECEIPT_CERTIFIED_FIELD) is True
        and all(row.get(field) == value for field, value in expected.items())
        and isinstance(score, (int, float))
        and not isinstance(score, bool)
        and math.isfinite(float(score))
        and tag_matches_candidate(workspace, row)
    )
