from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from ..evaluator_config import evaluator_repetitions
from ..git import git


@dataclass(frozen=True)
class TaskSetIdentity:
    digest: str
    members: tuple[str, ...]


def evaluation_split_name(evaluator: dict[str, Any], purpose: str = "candidate") -> str:
    if purpose == "anchor":
        return "sealed"
    value = evaluator.get("evaluation_split", "gate")
    if value not in {"train", "gate", "sealed"}:
        raise ValueError(f"unknown evaluator.evaluation_split: {value}")
    return str(value)


def task_set_identity(
    dataset: object,
    attempts: Any,
    members: tuple[str, ...],
    *,
    purpose: str = "candidate",
) -> TaskSetIdentity:
    normalized_members = tuple(sorted(set(members)))
    payload = {
        "dataset": str(dataset),
        "attempts": int(attempts),
        "tasks": list(normalized_members),
    }
    if purpose == "anchor":
        payload["split"] = "sealed"
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return TaskSetIdentity(digest=digest, members=normalized_members)


def effective_task_set_identity(
    checkout: Path,
    evaluator: dict[str, Any],
    *,
    purpose: str = "candidate",
    task_limit: int | None = None,
) -> TaskSetIdentity:
    if task_limit is not None and task_limit < 1:
        raise ValueError("task limit must be at least 1")
    configured_names = evaluator.get("task_names")
    if (
        purpose != "anchor"
        and isinstance(configured_names, list)
        and all(isinstance(name, str) and name for name in configured_names)
    ):
        return task_set_identity(
            evaluator.get("dataset", ""),
            evaluator_repetitions(evaluator),
            _limited_members(tuple(configured_names), task_limit),
            purpose=purpose,
        )
    split_path = checkout / "evaluator" / "splits.json"
    if split_path.is_file():
        verified = _verified_task_set_identity(
            split_path.read_text(),
            evaluator,
            purpose=purpose,
            source=str(split_path),
            task_limit=task_limit,
        )
        if verified is not None:
            return verified
    if purpose != "anchor" and isinstance(evaluator.get("task_file"), str) and evaluator["task_file"]:
        task_file = (checkout / evaluator["task_file"]).resolve()
        try:
            task_file.relative_to(checkout.resolve())
        except ValueError as error:
            raise ValueError("evaluator task_file escapes checkout") from error
        members = _limited_members(
            tuple(
                line.strip()
                for line in task_file.read_text().splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ),
            task_limit,
        )
    else:
        members = ()
        if split_path.is_file():
            try:
                members = _selected_split_members(
                    split_path.read_text(),
                    evaluator,
                    purpose=purpose,
                    source=str(split_path),
                    task_limit=task_limit,
                )
            except (OSError, json.JSONDecodeError, RuntimeError):
                members = ()
    attempts = evaluator_repetitions(evaluator)
    return task_set_identity(
        evaluator.get("dataset", ""),
        attempts,
        members,
        purpose=purpose,
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
        task_set = _fixed_task_set_identity(workspace, evaluator)
    except (OSError, RuntimeError, TypeError, ValueError, yaml.YAMLError):
        return None
    return {
        "evaluator_fingerprint": evaluator_tree,
        "task_set_hash": task_set.digest,
        "runtime_fingerprint": hashlib.sha256(runtime_pin.encode()).hexdigest(),
    }


def _fixed_task_set_identity(workspace: Path, evaluator: dict[str, Any]) -> TaskSetIdentity:
    configured_names = evaluator.get("task_names")
    if isinstance(configured_names, list) and all(isinstance(name, str) and name for name in configured_names):
        return task_set_identity(
            evaluator.get("dataset", ""),
            evaluator_repetitions(evaluator),
            tuple(configured_names),
        )
    split_text = _git_text(workspace, "show", "gen/0:evaluator/splits.json", strip=False)
    if split_text is not None:
        payload = json.loads(split_text)
        if isinstance(payload, dict) and payload.get("resolved") is True and payload.get("version") != 2:
            raise ValueError("resolved split manifest lacks certified content identity")
        verified = _verified_task_set_identity(split_text, evaluator, source="gen/0:evaluator/splits.json")
        if verified is not None:
            return verified
    return task_set_identity(
        evaluator.get("dataset", ""),
        evaluator_repetitions(evaluator),
        _fixed_task_members(workspace, evaluator),
    )


def _verified_task_set_identity(
    text: str,
    evaluator: dict[str, Any],
    *,
    purpose: str = "candidate",
    source: str,
    task_limit: int | None = None,
) -> TaskSetIdentity | None:
    payload = json.loads(text)
    if not isinstance(payload, dict) or payload.get("version") != 2:
        return None
    from ..splits import parse_manifest, selected_task_names
    from .datasets import selected_dataset_identity

    manifest = parse_manifest(text, source=source)
    split = evaluation_split_name(evaluator, purpose)
    selected = selected_dataset_identity(
        manifest,
        selected_task_names(manifest, split, limit=task_limit),
    )
    digest_payload = {
        "dataset_content_digest": selected.digest,
        "split": split,
        "task_members": list(selected.members),
        "repetitions": evaluator_repetitions(evaluator),
    }
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return TaskSetIdentity(digest, selected.members)


def _fixed_task_members(workspace: Path, evaluator: dict[str, Any]) -> tuple[str, ...]:
    names = evaluator.get("task_names")
    if isinstance(names, list) and all(isinstance(name, str) and name for name in names):
        return tuple(names)
    configured = evaluator.get("task_file")
    if isinstance(configured, str) and configured:
        path = PurePosixPath(configured)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("evaluator task_file escapes gen/0")
        contents = _git_text(workspace, "show", f"gen/0:{path.as_posix()}", strip=False)
        if contents is None:
            raise OSError("evaluator task_file is unavailable from gen/0")
        return tuple(
            line.strip() for line in contents.splitlines() if line.strip() and not line.lstrip().startswith("#")
        )
    split_text = _git_text(workspace, "show", "gen/0:evaluator/splits.json", strip=False)
    if split_text is None:
        return ()
    return _selected_split_members(
        split_text,
        evaluator,
        source="gen/0:evaluator/splits.json",
    )


def _selected_split_members(
    text: str,
    evaluator: dict[str, Any],
    *,
    purpose: str = "candidate",
    source: str,
    task_limit: int | None = None,
) -> tuple[str, ...]:
    payload = json.loads(text)
    if isinstance(payload, dict) and payload.get("version") in {1, 2}:
        from ..splits import parse_manifest, selected_task_names

        manifest = parse_manifest(text, source=source)
        return tuple(
            selected_task_names(
                manifest,
                evaluation_split_name(evaluator, purpose),
                limit=task_limit,
            )
        )
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    members = tasks.get(evaluation_split_name(evaluator, purpose)) if isinstance(tasks, dict) else None
    selected = tuple(members) if isinstance(members, list) and all(isinstance(name, str) for name in members) else ()
    return _limited_members(selected, task_limit)


def _limited_members(members: tuple[str, ...], task_limit: int | None) -> tuple[str, ...]:
    return members if task_limit is None else members[:task_limit]


def _git_text(workspace: Path, *args: str, strip: bool = True) -> str | None:
    result = git(workspace, *args, check=False)
    return None if result.returncode != 0 else (result.stdout.strip() if strip else result.stdout)
