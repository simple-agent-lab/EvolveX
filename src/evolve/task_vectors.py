from __future__ import annotations

from typing import Any, cast

from .evaluation import Outcome, TrialResult

TRIAL_STATUSES = {outcome.value for outcome in Outcome}


class TaskVectorError(ValueError):
    pass


def normalize_task_vector(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TaskVectorError("task vector must be an object")
    data = cast("dict[str, Any]", payload)
    if "schema_version" not in data:
        if not all(isinstance(key, str) and isinstance(value, bool) for key, value in data.items()):
            raise TaskVectorError("legacy task vector must map strings to booleans")
        return {
            "schema_version": 1,
            "tasks": {
                key: {
                    "trials": [
                        {"trial": 0, "status": Outcome.BENCHMARK_COMPLETE.value, "reward": 1.0 if value else 0.0}
                    ]
                }
                for key, value in sorted(data.items())
            },
        }
    if data.get("schema_version") != 1 or not isinstance(data.get("tasks"), dict):
        raise TaskVectorError("unsupported task vector schema")
    for task_id in data["tasks"]:
        if not isinstance(task_id, str):
            raise TaskVectorError(f"invalid task entry: {task_id}")
    tasks: dict[str, Any] = {}
    for task_id, task in sorted(data["tasks"].items()):
        if not isinstance(task_id, str) or not isinstance(task, dict) or not isinstance(task.get("trials"), list):
            raise TaskVectorError(f"invalid task entry: {task_id}")
        seen: set[int] = set()
        trials = []
        for raw in task["trials"]:
            if not isinstance(raw, dict) or isinstance(raw.get("trial"), bool) or not isinstance(raw.get("trial"), int):
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
            score_eligible = (
                status == Outcome.BENCHMARK_COMPLETE
                or status == Outcome.TIMEOUT
                and raw.get("owner") == "benchmark_agent"
            )
            if score_eligible and reward is None:
                raise TaskVectorError(f"{status} trial for {task_id} must have a numeric reward")
            diagnostic_failure = status in {
                Outcome.CANDIDATE_INVALID.value,
                Outcome.INFRASTRUCTURE_FAILED.value,
            } or bool(raw.get("exception_type") or raw.get("exception_message"))
            if not score_eligible and reward is not None and not diagnostic_failure:
                raise TaskVectorError(f"non-score-eligible trial for {task_id} must have a null reward")
            trials.append(dict(raw))
        tasks[task_id] = {**task, "trials": sorted(trials, key=lambda item: item["trial"])}
    return {"schema_version": 1, "tasks": tasks}


def validate_task_vector(payload: object) -> dict[str, Any]:
    return normalize_task_vector(payload)


def trial_results(payload: object) -> tuple[TrialResult, ...]:
    vector = normalize_task_vector(payload)
    return tuple(
        TrialResult(
            task_id=task_id,
            trial=int(raw["trial"]),
            outcome=Outcome(str(raw["status"])),
            reward=float(raw["reward"]) if raw.get("reward") is not None else None,
            owner=str(raw.get("owner") or "benchmark"),
            exception_type=str(raw["exception_type"]) if raw.get("exception_type") else None,
            exception_message=str(raw["exception_message"]) if raw.get("exception_message") else None,
        )
        for task_id, task in vector["tasks"].items()
        for raw in task["trials"]
    )


def task_passed(payload: object, task_id: str) -> bool | None:
    task = normalize_task_vector(payload)["tasks"].get(task_id)
    if not task:
        return None
    trials = task["trials"]
    if not trials or any(
        item.get("reward") is None
        or not (
            item["status"] == Outcome.BENCHMARK_COMPLETE
            or item["status"] == Outcome.TIMEOUT
            and item.get("owner") in {"benchmark_agent", "benchmark_verifier"}
        )
        for item in trials
    ):
        return None
    return all(float(item["reward"]) > 0 for item in trials)
