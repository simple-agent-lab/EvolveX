from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BranchIntent:
    source_generation: str
    source_tag: str
    source_commit: str
    target_generation: int
    target_genids: tuple[str, ...]
    created_at: str


def branch_intent_path(workspace: Path) -> Path:
    return workspace.resolve() / "runs" / "branch-intent.json"


def load_branch_intent(workspace: Path) -> BranchIntent | None:
    path = branch_intent_path(workspace)
    if not path.exists():
        return None
    try:
        raw: Any = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid branch intent {path}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError(f"unsupported branch intent schema in {path}")
    required = {
        "source_generation": str,
        "source_tag": str,
        "source_commit": str,
        "target_generation": int,
        "target_genids": list,
        "created_at": str,
    }
    for field, expected in required.items():
        if not isinstance(raw.get(field), expected):
            raise RuntimeError(f"invalid branch intent field {field} in {path}")
    if raw["target_generation"] < 1 or not raw["target_genids"]:
        raise RuntimeError(f"invalid branch intent target in {path}")
    return BranchIntent(
        source_generation=raw["source_generation"],
        source_tag=raw["source_tag"],
        source_commit=raw["source_commit"],
        target_generation=raw["target_generation"],
        target_genids=tuple(str(value) for value in raw["target_genids"]),
        created_at=raw["created_at"],
    )


def create_branch_intent(workspace: Path, intent: BranchIntent) -> BranchIntent:
    existing = load_branch_intent(workspace)
    if existing is not None:
        if existing == intent:
            return existing
        raise RuntimeError(
            f"conflicting branch intent: active gen/{existing.source_generation}, "
            f"requested gen/{intent.source_generation}"
        )
    payload = {"schema_version": SCHEMA_VERSION, **asdict(intent), "target_genids": list(intent.target_genids)}
    _atomic_write(branch_intent_path(workspace), payload)
    return intent


def consume_branch_intent(workspace: Path, intent: BranchIntent) -> None:
    path = branch_intent_path(workspace)
    existing = load_branch_intent(workspace)
    if existing is None:
        return
    if existing != intent:
        raise RuntimeError("branch intent changed before it could be consumed")
    path.unlink()


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
