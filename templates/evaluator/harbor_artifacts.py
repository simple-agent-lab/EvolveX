from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SAFE_ARTIFACTS = (
    "agent/mini-swe-agent.trajectory.json",
    "agent/mini-swe-agent.txt",
    "agent/trajectory.json",
    "trial.log",
    "verifier/reward.txt",
    "verifier/test-stdout.txt",
    "result.json",
    "exception.txt",
)
_CANDIDATE_MARKER = "EVOLVE_CANDIDATE_INVALID:"
_SAFE_ERROR_CODE = re.compile(r"[a-z0-9_]+")


def candidate_error_code(exception_info: object) -> str | None:
    if not isinstance(exception_info, dict):
        return None
    message = str(exception_info.get("exception_message") or "")
    if _CANDIDATE_MARKER not in message:
        return None
    code = message.partition(_CANDIDATE_MARKER)[2].strip().splitlines()[0].strip()
    return code if _SAFE_ERROR_CODE.fullmatch(code) else "candidate_invalid"


def collect_harbor_artifacts(jobs_dir: Path) -> tuple[dict[str, Any], dict[str, Any], list[float]]:
    trials = _load_task_trials(jobs_dir)
    return _build_task_vector(trials), _build_artifact_index(jobs_dir, trials), _scoring_rewards(trials)


def write_harbor_artifacts(jobs_dir: Path, run_dir: Path) -> list[float]:
    task_vector, artifact_index, rewards = collect_harbor_artifacts(jobs_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "task_vector.json").write_text(json.dumps(task_vector, indent=2, sort_keys=True) + "\n")
    (run_dir / "evaluation_artifacts.json").write_text(json.dumps(artifact_index, indent=2, sort_keys=True) + "\n")
    (run_dir / "cost.json").write_text(
        json.dumps({"usd": sum(float(trial["cost_usd"]) for trial in artifact_index["trials"])}, sort_keys=True) + "\n"
    )
    return rewards


def _load_task_trials(jobs_dir: Path) -> list[dict[str, Any]]:
    if not jobs_dir.exists():
        return []
    verifier_timeout_is_final_zero = _verifier_timeout_is_final_zero(jobs_dir)
    trials: list[dict[str, Any]] = []
    for result_path in sorted(jobs_dir.rglob("result.json")):
        try:
            result = json.loads(result_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(result, dict):
            continue
        task_name = result.get("task_name")
        trial_name = result.get("trial_name")
        if not isinstance(task_name, str) or not isinstance(trial_name, str):
            continue
        status, reward, owner = _trial_result(result, verifier_timeout_is_final_zero=verifier_timeout_is_final_zero)
        exception_info = result.get("exception_info")
        exception_type = None
        exception_message = None
        if isinstance(exception_info, dict):
            raw_type = exception_info.get("exception_type")
            raw_message = exception_info.get("exception_message")
            exception_type = str(raw_type) if raw_type else None
            exception_message = _exception_message(raw_message)
        trial_dir = result_path.parent
        trials.append(
            {
                "task_name": task_name,
                "trial_name": trial_name,
                "status": status,
                "reward": reward,
                "owner": owner,
                "exception_type": exception_type,
                "exception_message": exception_message,
                "cost_usd": _cost_usd(result),
                "trial_dir": trial_dir,
                "artifacts": _safe_artifacts(jobs_dir, trial_dir),
            }
        )
    return sorted(trials, key=lambda trial: (str(trial["task_name"]), str(trial["trial_name"])))


def _build_task_vector(trials: list[dict[str, Any]]) -> dict[str, Any]:
    tasks: dict[str, list[dict[str, Any]]] = {}
    for entry in trials:
        tasks.setdefault(str(entry["task_name"]), []).append(entry)
    serialized_tasks: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for task_name, task_trials in sorted(tasks.items()):
        serialized_trials: list[dict[str, Any]] = []
        for index, entry in enumerate(sorted(task_trials, key=lambda trial: str(trial["trial_name"]))):
            serialized = {
                "trial": index,
                "status": entry["status"],
                "reward": entry["reward"],
                "owner": entry["owner"],
            }
            if entry["exception_type"] is not None:
                serialized["exception_type"] = entry["exception_type"]
            if entry["exception_message"] is not None:
                serialized["exception_message"] = entry["exception_message"]
            serialized_trials.append(serialized)
        serialized_tasks[task_name] = {"trials": serialized_trials}
    return {"schema_version": 1, "tasks": serialized_tasks}


def _build_artifact_index(jobs_dir: Path, trials: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "jobs_dir": str(jobs_dir.resolve()),
        "trials": [
            {
                "task_name": entry["task_name"],
                "trial_name": entry["trial_name"],
                "cost_usd": entry["cost_usd"],
                "files": entry["artifacts"],
            }
            for entry in trials
        ],
    }


def _scoring_rewards(trials: list[dict[str, Any]]) -> list[float]:
    return [float(entry["reward"]) for entry in trials if entry["reward"] is not None]


def _reward(result: dict[str, Any]) -> float | None:
    reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    return float(reward) if isinstance(reward, (int, float)) and not isinstance(reward, bool) else None


def _verifier_timeout_is_final_zero(jobs_dir: Path) -> bool:
    configs = [path for path in jobs_dir.glob("*/config.json") if path.parent.parent == jobs_dir]
    if len(configs) != 1:
        return False
    try:
        payload = json.loads(configs[0].read_text())
        retry = payload.get("retry") if isinstance(payload, dict) else None
        excluded = set((retry or {}).get("exclude_exceptions") or [])
        return int((retry or {}).get("max_retries") or 0) >= 1 and "VerifierTimeoutError" not in excluded
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _trial_result(result: dict[str, Any], *, verifier_timeout_is_final_zero: bool) -> tuple[str, float | None, str]:
    exception = result.get("exception_info") or {}
    exception_type = str(exception.get("exception_type") or "")
    if exception_type in {"AgentTimeoutError", "AgentExecutionTimeoutError"}:
        return "timeout", 0.0, "benchmark_agent"
    if (
        exception_type == "VerifierTimeoutError"
        and verifier_timeout_is_final_zero
        and result.get("agent_result") is not None
    ):
        return "timeout", 0.0, "benchmark_verifier"
    if exception_type:
        if candidate_error_code(exception):
            return "candidate_invalid", None, "candidate"
        return "infrastructure_failed", None, "ambiguous"
    reward = _reward(result)
    if reward is not None:
        return "benchmark_complete", reward, "benchmark"
    return "infrastructure_failed", None, "evaluator"


def _cost_usd(result: dict[str, Any]) -> float:
    value = (result.get("agent_result") or {}).get("cost_usd")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _exception_message(value: object) -> str | None:
    if not value:
        return None
    message = str(value).strip().splitlines()[0].strip()
    return None if message.startswith("Traceback") else message or None


def _safe_artifacts(jobs_dir: Path, trial_dir: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for relative_path in SAFE_ARTIFACTS:
        path = trial_dir / relative_path
        if not path.is_file():
            continue
        payload = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(jobs_dir).as_posix(),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return files
