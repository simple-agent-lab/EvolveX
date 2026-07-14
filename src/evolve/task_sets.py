from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TaskSetIdentity:
    digest: str
    members: tuple[str, ...]


def effective_task_set_identity(
    checkout: Path, evaluator: dict[str, Any], *, purpose: str = "candidate"
) -> TaskSetIdentity:
    configured_names = evaluator.get("task_names")
    if isinstance(configured_names, list) and all(isinstance(name, str) and name for name in configured_names):
        members = tuple(sorted(set(configured_names)))
    elif isinstance(evaluator.get("task_file"), str) and evaluator["task_file"]:
        task_file = (checkout / evaluator["task_file"]).resolve()
        try:
            task_file.relative_to(checkout.resolve())
        except ValueError as error:
            raise ValueError("evaluator task_file escapes checkout") from error
        members = tuple(
            sorted(
                {
                    line.strip()
                    for line in task_file.read_text().splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                }
            )
        )
    else:
        members = ()
        split_path = checkout / "evaluator" / "splits.json"
        if purpose == "anchor" and split_path.is_file():
            try:
                manifest = json.loads(split_path.read_text())
                split_tasks = manifest.get("tasks", {}).get("sealed", [])
                if isinstance(split_tasks, list) and all(isinstance(name, str) for name in split_tasks):
                    members = tuple(sorted(set(split_tasks)))
            except (OSError, json.JSONDecodeError, AttributeError):
                members = ()
    try:
        attempts = int(evaluator.get("k", 1))
    except (TypeError, ValueError):
        attempts = 1
    payload = {"dataset": str(evaluator.get("dataset", "")), "attempts": attempts, "tasks": list(members)}
    if purpose == "anchor":
        payload["split"] = "sealed"
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return TaskSetIdentity(digest=digest, members=members)
