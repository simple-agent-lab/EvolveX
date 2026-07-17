from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .archive import RECEIPT_CERTIFIED_FIELD
from .git import git, tag_exists


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


def fixed_evaluation_identity(workspace: Path) -> dict[str, str] | None:
    evaluator_tree = _git_text(workspace, "rev-parse", "gen/0:evaluator")
    config_text = _git_text(workspace, "show", "gen/0:evolve.yaml", strip=False)
    runtime_pin = _git_text(workspace, "show", "gen/0:evaluator/runtime.pin", strip=False)
    if evaluator_tree is None or config_text is None or runtime_pin is None:
        return None
    try:
        loaded = yaml.safe_load(config_text)
        evaluator = loaded.get("evaluator") if isinstance(loaded, dict) else None
        if not isinstance(evaluator, dict):
            return None
        members = _fixed_task_members(workspace, evaluator)
        attempts = int(evaluator.get("k", 1))
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return None
    payload = {"dataset": str(evaluator.get("dataset", "")), "attempts": attempts, "tasks": list(members)}
    return {
        "evaluator_fingerprint": evaluator_tree,
        "task_set_hash": hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "runtime_fingerprint": hashlib.sha256(runtime_pin.encode()).hexdigest(),
    }


def _fixed_task_members(workspace: Path, evaluator: dict[str, Any]) -> tuple[str, ...]:
    names = evaluator.get("task_names")
    if isinstance(names, list) and all(isinstance(name, str) and name for name in names):
        return tuple(sorted(set(names)))
    configured = evaluator.get("task_file")
    if not isinstance(configured, str) or not configured:
        return ()
    path = PurePosixPath(configured)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("evaluator task_file escapes gen/0")
    contents = _git_text(workspace, "show", f"gen/0:{path.as_posix()}", strip=False)
    if contents is None:
        raise OSError("evaluator task_file is unavailable from gen/0")
    return tuple(
        sorted({line.strip() for line in contents.splitlines() if line.strip() and not line.lstrip().startswith("#")})
    )


def _git_text(workspace: Path, *args: str, strip: bool = True) -> str | None:
    result = git(workspace, *args, check=False)
    return None if result.returncode != 0 else (result.stdout.strip() if strip else result.stdout)
