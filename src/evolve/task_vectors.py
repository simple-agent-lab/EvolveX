from __future__ import annotations

from typing import Any

TRIAL_STATUSES = {"complete", "agent_timeout", "infra_failed", "cancelled"}


class TaskVectorError(ValueError):
    pass


def normalize_task_vector(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TaskVectorError("task vector must be an object")
    if "schema_version" not in payload:
        if not all(isinstance(key, str) and isinstance(value, bool) for key, value in payload.items()):
            raise TaskVectorError("legacy task vector must map strings to booleans")
        return {
            "schema_version": 1,
            "tasks": {
                key: {"trials": [{"trial": 0, "status": "complete", "reward": 1.0 if value else 0.0}]}
                for key, value in sorted(payload.items())
            },
        }
    if payload.get("schema_version") != 1 or not isinstance(payload.get("tasks"), dict):
        raise TaskVectorError("unsupported task vector schema")
    tasks: dict[str, Any] = {}
    for task_id, task in sorted(payload["tasks"].items()):
        if not isinstance(task_id, str) or not isinstance(task, dict) or not isinstance(task.get("trials"), list):
            raise TaskVectorError(f"invalid task entry: {task_id}")
        seen: set[int] = set()
        trials = []
        for raw in task["trials"]:
            if not isinstance(raw, dict) or not isinstance(raw.get("trial"), int):
                raise TaskVectorError(f"invalid trial for {task_id}")
            trial = int(raw["trial"])
            if trial in seen:
                raise TaskVectorError(f"duplicate trial {trial} for {task_id}")
            seen.add(trial)
            status = raw.get("status")
            reward = raw.get("reward")
            if status not in TRIAL_STATUSES:
                raise TaskVectorError(f"invalid status {status!r} for {task_id}")
            if reward is not None and (isinstance(reward, bool) or not isinstance(reward, (int, float))):
                raise TaskVectorError(f"invalid reward for {task_id} trial {trial}")
            trials.append(dict(raw))
        tasks[task_id] = {**task, "trials": sorted(trials, key=lambda item: item["trial"])}
    return {"schema_version": 1, "tasks": tasks}


def validate_task_vector(payload: object) -> dict[str, Any]:
    return normalize_task_vector(payload)


def task_passed(payload: object, task_id: str) -> bool | None:
    task = normalize_task_vector(payload)["tasks"].get(task_id)
    if not task:
        return None
    trials = task["trials"]
    if not trials or any(item["status"] != "complete" or item.get("reward") is None for item in trials):
        return None
    return all(float(item["reward"]) > 0 for item in trials)
