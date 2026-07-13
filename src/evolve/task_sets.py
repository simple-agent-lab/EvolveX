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


def effective_task_set_identity(checkout: Path, evaluator: dict[str, Any]) -> TaskSetIdentity:
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
    try:
        attempts = int(evaluator.get("k", 1))
    except (TypeError, ValueError):
        attempts = 1
    payload = {"dataset": str(evaluator.get("dataset", "")), "attempts": attempts, "tasks": list(members)}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return TaskSetIdentity(digest=digest, members=members)
