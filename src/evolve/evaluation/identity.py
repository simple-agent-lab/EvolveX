from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

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
    task_digests: dict[str, str] | None = None,
) -> TaskSetIdentity:
    normalized_members = tuple(sorted(set(members)))
    payload = {
        "dataset": str(dataset),
        "attempts": int(attempts),
        "tasks": list(normalized_members),
    }
    if task_digests:
        missing = [name for name in normalized_members if name not in task_digests]
        if missing:
            raise ValueError(f"split manifest has no content digest for tasks: {', '.join(missing)}")
        payload["task_digests"] = {name: task_digests[name] for name in normalized_members}
    if purpose == "anchor":
        payload["split"] = "sealed"
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return TaskSetIdentity(digest=digest, members=normalized_members)


def effective_task_set_identity(
    checkout: Path, evaluator: dict[str, Any], *, purpose: str = "candidate"
) -> TaskSetIdentity:
    manifest = _checkout_split_manifest(checkout)
    configured_names = evaluator.get("task_names")
    if isinstance(configured_names, list) and all(isinstance(name, str) and name for name in configured_names):
        members = tuple(configured_names)
    elif isinstance(evaluator.get("task_file"), str) and evaluator["task_file"]:
        task_file = (checkout / evaluator["task_file"]).resolve()
        try:
            task_file.relative_to(checkout.resolve())
        except ValueError as error:
            raise ValueError("evaluator task_file escapes checkout") from error
        members = tuple(
            line.strip()
            for line in task_file.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    else:
        members = ()
        if manifest is not None:
            split_tasks = manifest.get("tasks", {}).get(evaluation_split_name(evaluator, purpose), [])
            if isinstance(split_tasks, list) and all(isinstance(name, str) for name in split_tasks):
                members = tuple(split_tasks)
    try:
        attempts = int(evaluator.get("k", 1))
    except (TypeError, ValueError):
        attempts = 1
    return task_set_identity(
        evaluator.get("dataset", ""),
        attempts,
        members,
        purpose=purpose,
        task_digests=_manifest_task_digests(manifest),
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
        manifest = _fixed_split_manifest(workspace)
        members = _fixed_task_members(workspace, evaluator, manifest)
        if (
            manifest is not None
            and manifest.get("resolved") is True
            and members
            and _manifest_task_digests(manifest) is None
        ):
            return None
        task_set = task_set_identity(
            evaluator.get("dataset", ""),
            evaluator.get("k", 1),
            members,
            task_digests=_manifest_task_digests(manifest),
        )
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return None
    return {
        "evaluator_fingerprint": evaluator_tree,
        "task_set_hash": task_set.digest,
        "runtime_fingerprint": hashlib.sha256(runtime_pin.encode()).hexdigest(),
    }


def _fixed_task_members(
    workspace: Path, evaluator: dict[str, Any], manifest: dict[str, Any] | None = None
) -> tuple[str, ...]:
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
    if manifest is None:
        return ()
    split_tasks = manifest.get("tasks", {}).get(evaluation_split_name(evaluator), [])
    if not isinstance(split_tasks, list) or not all(isinstance(name, str) for name in split_tasks):
        return ()
    return tuple(split_tasks)


def _checkout_split_manifest(checkout: Path) -> dict[str, Any] | None:
    split_path = checkout / "evaluator" / "splits.json"
    if not split_path.is_file():
        return None
    try:
        payload = json.loads(split_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _fixed_split_manifest(workspace: Path) -> dict[str, Any] | None:
    split_text = _git_text(workspace, "show", "gen/0:evaluator/splits.json", strip=False)
    if split_text is None:
        return None
    payload = json.loads(split_text)
    return payload if isinstance(payload, dict) else None


def _manifest_task_digests(manifest: dict[str, Any] | None) -> dict[str, str] | None:
    if manifest is None or manifest.get("version") != 2:
        return None
    task_digests = manifest.get("task_digests")
    if not isinstance(task_digests, dict) or not task_digests:
        return None
    if any(not isinstance(name, str) or not isinstance(digest, str) for name, digest in task_digests.items()):
        raise ValueError("invalid split manifest task content digests")
    return dict(task_digests)


def _git_text(workspace: Path, *args: str, strip: bool = True) -> str | None:
    result = git(workspace, *args, check=False)
    return None if result.returncode != 0 else (result.stdout.strip() if strip else result.stdout)
