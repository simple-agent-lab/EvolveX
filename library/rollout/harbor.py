"""Run the current checkout through Harbor and distill meta-agent feedback."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, RolloutOperator, RolloutResult
from evolve.host_runtime import uv_run
from evolve.splits import harbor_task_pattern, load_manifest, select_dataset_tasks
from library._shared.config import (
    boolean,
    config_object,
    mapping,
    nonnegative_int,
    positive_float,
    positive_int,
    reject_unknown,
    string,
    string_list,
)

_CONFIG_KEYS = {
    "budget_tasks",
    "task_sampling",
    "n_concurrent",
    "agent_setup_timeout_multiplier",
    "agent_timeout_multiplier",
    "verifier_timeout_multiplier",
    "max_retries",
    "field_limit",
    "pass_threshold",
    "environment",
    "environment_kwargs",
    "agent",
    "agent_env",
    "model",
    "include_task_name",
    "jobs_dir",
    "path",
    "split",
    "task_names",
    "reuse_completed",
    "seed",
}


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, _CONFIG_KEYS)
    normalized: dict[str, object] = {
        "budget_tasks": positive_int(config, "budget_tasks", 8),
        "task_sampling": string(config, "task_sampling", "head"),
        "field_limit": positive_int(config, "field_limit", 2000),
        "seed": _integer(config, "seed", 0),
        "reuse_completed": boolean(config, "reuse_completed", False),
    }
    if normalized["task_sampling"] not in {"head", "generation_shuffle"}:
        raise ValueError("task_sampling must be 'head' or 'generation_shuffle'")
    threshold = config.get("pass_threshold", 1.0)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(float(threshold)):
        raise ValueError("pass_threshold must be a finite number")
    normalized["pass_threshold"] = float(threshold)
    for key in ("n_concurrent",):
        if key in config:
            normalized[key] = positive_int(config, key, 1)
    for key in ("agent_setup_timeout_multiplier", "agent_timeout_multiplier", "verifier_timeout_multiplier"):
        if key in config:
            normalized[key] = positive_float(config, key, 1.0)
    if "max_retries" in config:
        normalized["max_retries"] = nonnegative_int(config, "max_retries", 0)
    for key in ("environment", "agent", "model", "include_task_name", "jobs_dir", "path", "split"):
        if key in config:
            normalized[key] = string(config, key, "")
    for key in ("environment_kwargs", "agent_env"):
        if key in config:
            normalized[key] = mapping(config, key, {})
    if "task_names" in config:
        names = string_list(config, "task_names", [])
        if not names:
            raise ValueError("task_names must be a non-empty list of task names")
        normalized["task_names"] = names
    return normalized


def _integer(config: dict[str, object], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


_INFRA_EXCEPTION_MARKERS = (
    "infrastructure",
    "verifier",
    "environment",
    "docker",
    "build",
    "download",
    "network",
)
_WRAPPER_MARKERS = ("<environment_context>", "<recommended_plugins>", "<permissions instructions>")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b([a-z0-9_-]*(?:api[_-]?key|access[_-]?token|auth(?:orization)?|secret|password))\b"
    r"([\"']?)(\s*[:=]\s*)([^\s,;}]+)"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SENSITIVE_ENV_NAME = re.compile(r"(?i)(?:proxy|api[_-]?key|access[_-]?token|token|secret|password|authorization|auth)")
_TRACE_EVENT_LIMIT = 32
_PROXY_ENV = (
    ("EVOLVE_HARBOR_HTTP_PROXY", "http_proxy", "HTTP_PROXY"),
    ("EVOLVE_HARBOR_HTTPS_PROXY", "https_proxy", "HTTPS_PROXY"),
    ("EVOLVE_HARBOR_NO_PROXY", "no_proxy", "NO_PROXY"),
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _redact(text: str, environment: Mapping[str, str] | None = None) -> str:
    configured = os.environ if environment is None else environment
    values = {value for name, value in configured.items() if _SENSITIVE_ENV_NAME.search(name) and len(value) >= 8}
    for value in sorted(values, key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    text = _BEARER.sub("Bearer [REDACTED]", text)
    return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED]", text)


def _clip(value: object, limit: int, *, tail: bool = False) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, sort_keys=True)
        except (TypeError, ValueError):
            text = str(value)
    text = _redact(text.strip())
    if len(text) <= limit:
        return text
    marker = f"\n...[truncated {len(text) - limit} chars]...\n"
    kept = max(1, limit - len(marker))
    return marker + text[-kept:] if tail else text[:kept] + marker


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_text(path: Path, limit: int, *, tail: bool = False) -> str:
    try:
        return _clip(path.read_text(errors="replace"), limit, tail=tail)
    except OSError:
        return ""


def _load_eval_env(checkout: Path) -> dict[str, str]:
    path = checkout / "evaluator" / "eval.env"
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw = stripped.split("=", 1)
        try:
            parts = shlex.split(raw, posix=True)
            value = " ".join(parts) if parts else ""
        except ValueError:
            value = raw.strip().strip("\"'")
        values[key.strip()] = os.path.expanduser(os.path.expandvars(value))
    return values


def _agent_env_entries(checkout: Path) -> list[str]:
    path = checkout / "evaluator" / "agent.env"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def _reward(payload: dict[str, Any], trial_dir: Path) -> float | None:
    verifier = payload.get("verifier_result")
    rewards = verifier.get("rewards") if isinstance(verifier, dict) else None
    reward = rewards.get("reward") if isinstance(rewards, dict) else None
    if isinstance(reward, (int, float)) and not isinstance(reward, bool):
        return float(reward)
    reward_path = trial_dir / "verifier" / "reward.txt"
    try:
        return float(reward_path.read_text().strip()) if reward_path.exists() else None
    except (OSError, ValueError):
        return None


def _outcome(reward: float | None, exception_type: str, pass_threshold: float) -> str:
    if reward is not None:
        return "passed" if reward >= pass_threshold else "failed"
    lowered = exception_type.lower()
    if any(marker in lowered for marker in _INFRA_EXCEPTION_MARKERS):
        return "infra_error"
    if exception_type:
        return "agent_error"
    return "incomplete"


def _duration_seconds(value: object) -> float | None:
    if not isinstance(value, dict):
        return None
    try:
        start = datetime.fromisoformat(str(value["started_at"]).replace("Z", "+00:00"))
        finish = datetime.fromisoformat(str(value["finished_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return None
    return round((finish - start).total_seconds(), 3)


def _codex_session_details(trial_dir: Path, field_limit: int) -> dict[str, Any]:
    """Extract an ordered trace from Harbor's Codex session JSONL fallback."""
    instructions: list[str] = []
    messages: list[str] = []
    tool_calls: list[dict[str, str]] = []
    observations: list[str] = []
    events: list[dict[str, Any]] = []
    trajectory_events: list[dict[str, Any]] = []
    sessions = trial_dir / "agent" / "sessions"
    paths = sorted(sessions.rglob("*.jsonl")) if sessions.exists() else []
    for path in paths:
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line_index, line in enumerate(lines):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            outer_type = str(row.get("type") or "")
            event_type = str(payload.get("type") or "")
            timestamp = str(row.get("timestamp") or "")
            if outer_type == "event_msg" and event_type == "user_message":
                message = payload.get("message")
                wrapper = isinstance(message, str) and any(marker in message for marker in _WRAPPER_MARKERS)
                if isinstance(message, str) and message.strip() and not wrapper:
                    clipped = _clip(message, field_limit)
                    instructions.append(clipped)
                    events.append(
                        {
                            "index": line_index,
                            "timestamp": timestamp,
                            "type": "message",
                            "source": "user",
                            "message": clipped,
                        }
                    )
                    trajectory_events.append(events[-1])
            elif outer_type == "event_msg" and event_type == "agent_message":
                message = payload.get("message")
                if isinstance(message, str) and message.strip():
                    clipped = _clip(message, field_limit)
                    messages.append(clipped)
                    events.append(
                        {
                            "index": line_index,
                            "timestamp": timestamp,
                            "type": "message",
                            "source": "agent",
                            "message": clipped,
                        }
                    )
                    trajectory_events.append(events[-1])
            elif outer_type == "response_item" and event_type in {"function_call", "custom_tool_call"}:
                call = {
                    "name": str(payload.get("name") or "unknown"),
                    "arguments": _clip(payload.get("arguments") or payload.get("input") or {}, field_limit),
                }
                tool_calls.append(call)
                events.append(
                    {
                        "index": line_index,
                        "timestamp": timestamp,
                        "type": "tool_call",
                        "call_id": str(payload.get("call_id") or ""),
                        **call,
                    }
                )
                trajectory_events.append(events[-1])
            elif outer_type == "response_item" and event_type in {
                "function_call_output",
                "custom_tool_call_output",
            }:
                raw_output = payload.get("output") or ""
                output = _clip(raw_output, field_limit, tail=True)
                trajectory_output = _clip(raw_output, field_limit)
                observations.append(output)
                events.append(
                    {
                        "index": line_index,
                        "timestamp": timestamp,
                        "type": "tool_result",
                        "call_id": str(payload.get("call_id") or ""),
                        "observation": output,
                    }
                )
                trajectory_events.append({**events[-1], "observation": trajectory_output})
    return {
        "instruction": instructions[-1] if instructions else "",
        "agent_messages": messages[-4:],
        "tool_calls": tool_calls[-8:],
        "observations": observations[-8:],
        "events": events[-_TRACE_EVENT_LIMIT:],
        "trajectory_events": trajectory_events,
        "raw_agent_output": "",
    }


def _trajectory_details(trial_dir: Path, field_limit: int) -> dict[str, Any]:
    trajectory = _read_json(trial_dir / "agent" / "trajectory.json")
    steps = trajectory.get("steps")
    if not isinstance(steps, list):
        steps = []

    instructions: list[str] = []
    messages: list[str] = []
    tool_calls: list[dict[str, str]] = []
    observations: list[str] = []
    events: list[dict[str, Any]] = []
    trajectory_events: list[dict[str, Any]] = []
    for step_index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        source = step.get("source")
        message = step.get("message")
        wrapper_message = isinstance(message, str) and any(marker in message for marker in _WRAPPER_MARKERS)
        if source == "user" and isinstance(message, str) and not wrapper_message:
            instructions.append(_clip(message, field_limit))
        if source == "agent" and isinstance(message, str) and message.strip():
            messages.append(_clip(message, field_limit))
        step_calls: list[dict[str, str]] = []
        calls = step.get("tool_calls")
        if isinstance(calls, list):
            for call in calls:
                if not isinstance(call, dict):
                    continue
                normalized_call = {
                    "name": str(call.get("function_name") or call.get("name") or "unknown"),
                    "arguments": _clip(call.get("arguments") or {}, field_limit),
                }
                tool_calls.append(normalized_call)
                step_calls.append(normalized_call)
        step_observations: list[str] = []
        trajectory_observations: list[str] = []
        observation = step.get("observation")
        results = observation.get("results") if isinstance(observation, dict) else None
        if isinstance(results, list):
            for result in results:
                if isinstance(result, dict) and result.get("content"):
                    raw_content = result["content"]
                    content = _clip(raw_content, field_limit, tail=True)
                    observations.append(content)
                    step_observations.append(content)
                    trajectory_observations.append(_clip(raw_content, field_limit))
        if not wrapper_message and (message or step_calls or step_observations):
            events.append(
                {
                    "step": step_index,
                    "source": str(source or "unknown"),
                    "message": _clip(message or "", field_limit),
                    "tool_calls": step_calls,
                    "observations": step_observations,
                }
            )
            trajectory_events.append(
                {
                    **events[-1],
                    "observations": trajectory_observations,
                }
            )

    if not steps:
        codex_details = _codex_session_details(trial_dir, field_limit)
        if codex_details["events"]:
            return codex_details

    raw_agent_output = ""
    if not messages and not tool_calls:
        candidates = sorted((trial_dir / "agent").glob("*.txt")) if (trial_dir / "agent").exists() else []
        raw_agent_output = "\n".join(_read_text(path, field_limit, tail=True) for path in candidates[:2])
    return {
        "instruction": instructions[-1] if instructions else "",
        "agent_messages": messages[-4:],
        "tool_calls": tool_calls[-8:],
        "observations": observations[-8:],
        "events": events[-_TRACE_EVENT_LIMIT:],
        "trajectory_events": trajectory_events,
        "raw_agent_output": raw_agent_output,
    }


def _verifier_output(trial_dir: Path, field_limit: int) -> str:
    verifier_dir = trial_dir / "verifier"
    if not verifier_dir.exists():
        return ""
    parts: list[str] = []
    for path in sorted(verifier_dir.rglob("*")):
        if not path.is_file() or path.name in {"reward.txt", "reward.json"}:
            continue
        text = _read_text(path, field_limit, tail=True)
        if text:
            parts.append(f"[{path.relative_to(verifier_dir).as_posix()}]\n{text}")
    return _clip("\n\n".join(parts), field_limit * 2, tail=True)


def _artifact_inventory(trial_dir: Path) -> dict[str, list[str]]:
    inventory: dict[str, list[str]] = {}
    for name in ("agent", "verifier"):
        root = trial_dir / name
        inventory[name] = (
            [path.relative_to(root).as_posix() for path in sorted(root.rglob("*")) if path.is_file()]
            if root.exists()
            else []
        )
    return inventory


def _artifact_refs(trial_dir: Path) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for area in ("agent", "verifier"):
        root = trial_dir / area
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name in {"reward.txt", "reward.json"}:
                continue
            relative = path.relative_to(root).as_posix()
            suffix = path.suffix.lower().lstrip(".")
            refs.append({"kind": suffix or "file", "path": f"{area}/{relative}"})
    return refs


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workspace_relative(path: Path, workspace: Path | None) -> str | None:
    if workspace is None:
        return None
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return None


def _trajectory_archive_name(trial_name: str, digest: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", trial_name).strip("._-") or "trial"
    return f"{stem[:96]}-{digest[:16]}.json"


def _trajectory_reference(
    trial_dir: Path,
    *,
    trial_name: str,
    workspace: Path | None,
    trajectory_archive_dir: Path | None,
) -> dict[str, Any]:
    source = trial_dir / "agent" / "trajectory.json"
    if not source.is_file():
        return {"format": "atif", "status": "missing"}
    try:
        digest = _file_sha256(source)
    except OSError:
        return {"format": "atif", "status": "unreadable"}

    retained = source
    relative = _workspace_relative(source, workspace)
    if workspace is not None and relative is None:
        if trajectory_archive_dir is None:
            return {"format": "atif", "status": "external"}
        trajectory_archive_dir.mkdir(parents=True, exist_ok=True)
        retained = trajectory_archive_dir / _trajectory_archive_name(trial_name, digest)
        if not retained.exists():
            shutil.copyfile(source, retained)
            retained.chmod(0o600)
        if _file_sha256(retained) != digest:
            raise SystemExit(f"retained trajectory digest mismatch: {retained}")
        relative = _workspace_relative(retained, workspace)
        if relative is None:
            raise SystemExit("trajectory archive directory must stay inside the workspace")

    payload = _read_json(retained)
    steps = payload.get("steps")
    reference: dict[str, Any] = {
        "format": "atif",
        "status": "available" if isinstance(steps, list) else "invalid",
        "path": relative if relative is not None else str(retained),
        "sha256": digest,
    }
    if isinstance(steps, list):
        reference["steps"] = len(steps)
    return reference


def _task_instruction(tasks_dir: Path | None, task_name: str, field_limit: int) -> str:
    if tasks_dir is None:
        return ""
    leaf = task_name.rsplit("/", 1)[-1]
    for candidate in (tasks_dir / task_name / "instruction.md", tasks_dir / leaf / "instruction.md"):
        if candidate.is_file():
            return _read_text(candidate, field_limit)
    return ""


def _artifact_evidence(
    trial_dir: Path,
    *,
    instruction: str,
    reward: float | None,
    trajectory: dict[str, Any],
) -> dict[str, Any]:
    evaluation = _read_json(trial_dir / "verifier" / "evaluation.json")
    refs = _artifact_refs(trial_dir)
    criteria = evaluation.get("criteria")
    criteria = criteria if isinstance(criteria, dict) else {}
    judgments = [
        {"rubric_id": str(name), "score": float(score), "hard_failure": False}
        for name, score in sorted(criteria.items())
        if isinstance(score, (int, float)) and not isinstance(score, bool)
    ]
    hard_failures = evaluation.get("hard_failures")
    hard_failures = hard_failures if isinstance(hard_failures, list) else []
    for failure in hard_failures:
        message = str(failure)
        judgments.append(
            {
                "rubric_id": message.split(":", 1)[0].strip() or "hard_failure",
                "score": 0.0,
                "hard_failure": True,
                "feedback": message,
            }
        )
    metrics: dict[str, float | None] = {"reward": reward}
    for name in ("score", "raw_weighted_score"):
        value = evaluation.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[name] = float(value)
    primary = next((ref["path"] for ref in refs if ref["kind"] == "svg"), None)
    feedback_message = evaluation.get("feedback")
    if isinstance(feedback_message, str) and feedback_message.strip():
        feedback = {"message": feedback_message.strip()}
    else:
        feedback = {
            "summary": str(evaluation.get("summary") or ""),
            "improvement": str(evaluation.get("improvement_feedback") or ""),
        }
    return {
        "evidence_schema_version": 1,
        "inputs": {"instruction": instruction},
        "outputs": {"primary_artifact": primary},
        "artifacts": refs,
        "judgments": judgments,
        "metrics": metrics,
        "feedback": feedback,
        "execution": {
            "trajectory_available": trajectory.get("status") == "available",
            "trajectory": trajectory,
        },
    }


def collect_cases(
    jobs_dir: Path,
    field_limit: int = 2000,
    pass_threshold: float = 1.0,
    tasks_dir: Path | None = None,
    workspace: Path | None = None,
    trajectory_archive_dir: Path | None = None,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    if not jobs_dir.exists():
        return cases
    replay_results = sorted(jobs_dir.rglob("evolve-replay.json"))
    result_paths = replay_results or sorted(jobs_dir.rglob("result.json"))
    for result_path in result_paths:
        payload = _read_json(result_path)
        if not payload.get("trial_name") or not payload.get("task_name"):
            continue
        trial_dir = result_path.parent
        exception = payload.get("exception_info")
        exception = exception if isinstance(exception, dict) else {}
        exception_type = str(exception.get("exception_type") or "")
        reward = _reward(payload, trial_dir)
        agent_result = payload.get("agent_result")
        agent_result = agent_result if isinstance(agent_result, dict) else {}
        verifier_result = payload.get("verifier_result")
        verifier_result = verifier_result if isinstance(verifier_result, dict) else {}
        verifier_rewards = verifier_result.get("rewards")
        verifier_rewards = verifier_rewards if isinstance(verifier_rewards, dict) else {}
        details = _trajectory_details(trial_dir, field_limit)
        instruction = details["instruction"] or _task_instruction(tasks_dir, str(payload.get("task_name")), field_limit)
        trajectory = _trajectory_reference(
            trial_dir,
            trial_name=str(payload.get("trial_name")),
            workspace=workspace,
            trajectory_archive_dir=trajectory_archive_dir,
        )
        evidence = _artifact_evidence(
            trial_dir,
            instruction=instruction,
            reward=reward,
            trajectory=trajectory,
        )
        cases.append(
            {
                "trial_name": str(payload.get("trial_name")),
                "task_name": str(payload.get("task_name")),
                "reward": reward,
                "outcome": _outcome(reward, exception_type, pass_threshold),
                "instruction": instruction,
                **evidence,
                "agent_messages": details["agent_messages"],
                "tool_calls": details["tool_calls"],
                "observations": details["observations"],
                "events": details["events"],
                "trajectory_events": details["trajectory_events"],
                "raw_agent_output": details["raw_agent_output"],
                "verifier_output": _verifier_output(trial_dir, field_limit),
                "verifier_rewards": {
                    str(key): (_clip(value, field_limit) if isinstance(value, str) else value)
                    for key, value in verifier_rewards.items()
                    if isinstance(value, (str, int, float, bool)) or value is None
                },
                "exception": {
                    "type": exception_type,
                    "message": _clip(exception.get("exception_message") or "", field_limit),
                },
                "usage": {
                    "input_tokens": agent_result.get("n_input_tokens"),
                    "cache_tokens": agent_result.get("n_cache_tokens"),
                    "output_tokens": agent_result.get("n_output_tokens"),
                    "cost_usd": agent_result.get("cost_usd"),
                },
                "timing_s": {
                    name: _duration_seconds(payload.get(name))
                    for name in ("environment_setup", "agent_setup", "agent_execution", "verifier")
                },
                "artifact_inventory": _artifact_inventory(trial_dir),
                "result_path": str(result_path),
            }
        )
    return cases


def require_rollout_cases(cases: list[dict[str, Any]], *, returncode: int, harbor_log: Path) -> None:
    if not cases:
        raise SystemExit(f"harbor rollout produced no trial results (exit {returncode}); see {harbor_log}")


def _jobs_root(ctx: OperatorContext) -> Path:
    configured = ctx.config.get("jobs_dir") or os.environ.get("EVOLVE_ROLLOUT_JOBS_DIR")
    return Path(str(configured)).expanduser() if configured else ctx.workspace / "runs" / "harbor-rollouts"


_OUTCOME_ORDER = ("failed", "agent_error", "infra_error", "incomplete", "passed")


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def _nonnegative_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def _configured_max_retries(config: Mapping[str, Any], eval_env: Mapping[str, str]) -> int:
    value = config["max_retries"] if "max_retries" in config else eval_env.get("EVOLVE_HARBOR_MAX_RETRIES")
    return _nonnegative_int(value, 0)


def _float_value(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _run_timeout() -> float | None:
    try:
        outer = float(os.environ.get("EVOLVE_OPERATOR_TIMEOUT_S", ""))
    except ValueError:
        return None
    return max(0.1, outer - min(5.0, max(0.5, outer * 0.05)))


def _reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _task_leaf(task_name: str) -> str:
    return task_name.rsplit("/", 1)[-1]


def _with_missing_result_placeholders(cases: list[dict[str, Any]], selected_tasks: list[str]) -> list[dict[str, Any]]:
    """Represent absent frozen-split results so trace analysis cannot silently ignore them."""
    completed = [dict(case) for case in cases]
    observed_leaves = {_task_leaf(str(case.get("task_name"))) for case in completed if case.get("task_name")}
    for task_name in selected_tasks:
        if _task_leaf(task_name) in observed_leaves:
            continue
        completed.append(
            {
                "trial_name": f"missing::{task_name}",
                "task_name": task_name,
                "reward": None,
                "outcome": "incomplete",
                "exception": {
                    "type": "MissingRolloutResult",
                    "message": "Harbor produced no result.json for the selected task",
                },
                "execution": {
                    "trajectory_available": False,
                    "trajectory": {"format": "atif", "status": "missing"},
                },
                "result_path": "",
            }
        )
    return completed


def _batch_failure_case(harbor_log: Path, returncode: int, field_limit: int) -> dict[str, Any]:
    """Keep batch-level Harbor failures inspectable when no task result exists."""
    message = _read_text(harbor_log, field_limit, tail=True)
    return {
        "trial_name": "harbor-batch",
        "task_name": "harbor-batch",
        "reward": None,
        "outcome": "infra_error" if returncode else "incomplete",
        "instruction": "",
        "agent_messages": [],
        "tool_calls": [],
        "observations": [],
        "events": [],
        "trajectory_events": [],
        "execution": {
            "trajectory_available": False,
            "trajectory": {"format": "atif", "status": "missing"},
        },
        "raw_agent_output": message,
        "verifier_output": "",
        "verifier_rewards": {},
        "exception": {
            "type": "HarborBatchError" if returncode else "MissingRolloutResult",
            "message": message or f"Harbor produced no task result (exit {returncode})",
        },
        "usage": {},
        "timing_s": {},
        "artifact_inventory": {},
        "result_path": "",
    }


def _batch_command(
    base_command: list[str],
    *,
    jobs_dir: Path,
    n_concurrent: int,
    budget_tasks: int,
    task_selectors: list[str],
    include_task: object = None,
) -> list[str]:
    command = [
        *base_command,
        "--jobs-dir",
        str(jobs_dir),
        "-n",
        str(min(n_concurrent, budget_tasks)),
        "--n-tasks",
        str(budget_tasks),
    ]
    if task_selectors:
        for task_name in task_selectors:
            command.extend(["--include-task-name", harbor_task_pattern(task_name)])
    elif include_task:
        command.extend(["--include-task-name", str(include_task)])
    return command


def _append_agent_env(command: list[str], checkout: Path, config: dict[str, Any]) -> None:
    for override, lower, upper in _PROXY_ENV:
        value = os.environ.get(override) or os.environ.get(lower) or os.environ.get(upper)
        if value:
            for key in (lower, upper):
                command.extend(["--ae", f"{key}={value}", "--ve", f"{key}={value}"])
    values = _load_eval_env(checkout)
    agent_env = checkout / "evaluator" / "agent.env"
    if agent_env.is_file():
        for line in agent_env.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value
    configured = config.get("agent_env")
    if isinstance(configured, dict):
        values.update({str(key): str(value) for key, value in configured.items()})
    for key, value in values.items():
        if key.startswith("EVOLVE_HARBOR_") or key.startswith("EVOLVE_EVALUATOR_"):
            continue
        command.extend(["--ae", f"{key}={value}"])


def _run_harbor(command: list[str], checkout: Path, log_path: Path, env: dict[str, str]) -> int:
    start = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=checkout,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        bufsize=1,
        umask=0o077,
    )
    chunks: list[str] = []

    def consume_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            chunks.append(line)
            if os.environ.get("EVOLVE_LIVE_OUTPUT") == "1":
                print(_redact(line), end="", flush=True)

    reader = threading.Thread(target=consume_output, daemon=True)
    reader.start()
    try:
        process.wait(timeout=_run_timeout())
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()
        process.wait()
        chunks.append("\nharbor rollout timed out\n")
    reader.join()
    output = "".join(chunks)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(_redact(f"wall_s={time.monotonic() - start:.3f}\n{output or ''}"))
    log_path.chmod(0o600)
    return process.returncode if process.returncode is not None else 1


def _select_train_tasks(
    manifest_path: Path,
    dataset: str,
    budget_tasks: int,
    requested: object = None,
    *,
    sampling: str = "head",
    sampling_key: str = "0",
) -> list[str]:
    """Resolve a bounded train batch, optionally preserving an exact prior batch."""
    all_train, _ = select_dataset_tasks(manifest_path, dataset, "train", limit=None)
    if requested is None:
        if sampling == "head":
            ordered = all_train
        elif sampling == "generation_shuffle":
            ordered = sorted(
                all_train,
                key=lambda name: hashlib.sha256(f"{sampling_key}\0{name}".encode()).hexdigest(),
            )
        else:
            raise ValueError("task_sampling must be 'head' or 'generation_shuffle'")
        return ordered[:budget_tasks]
    if (
        not isinstance(requested, list)
        or not requested
        or not all(isinstance(item, str) and item for item in requested)
    ):
        raise ValueError("task_names must be a non-empty list of task names")
    train_set = set(all_train)
    normalized: list[str] = []
    unknown: list[str] = []
    for name in requested:
        if name in train_set:
            normalized.append(name)
            continue
        leaf = name.rsplit("/", 1)[-1] if "/" in name else ""
        if leaf in train_set:
            normalized.append(leaf)
        else:
            unknown.append(name)
    if unknown:
        raise ValueError("task_names must come from the frozen train split: " + ", ".join(unknown))
    if len(set(normalized)) != len(normalized):
        raise ValueError("task_names must not contain duplicates")
    return normalized


def _completed_rollout(ctx: OperatorContext) -> RolloutResult | None:
    if ctx.config.get("reuse_completed") is not True:
        return None
    rollout_dir = ctx.run_dir / "rollout"
    try:
        summary = json.loads((rollout_dir / "summary.json").read_text())
        artifacts = json.loads((rollout_dir / "artifacts.json").read_text())
        cases = json.loads((rollout_dir / "cases.json").read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(summary, dict)
        or summary.get("variant") != "harbor"
        or not isinstance(artifacts, list)
        or not all(isinstance(item, str) and item for item in artifacts)
        or "rollout/cases.json" not in artifacts
        or not isinstance(cases, list)
        or not cases
        or summary.get("tasks_observed") != len(cases)
    ):
        return None
    return RolloutResult(summary=summary, artifacts=artifacts)


class HarborRollout(RolloutOperator):
    def rollout(self, checkout: Path, ctx: OperatorContext) -> RolloutResult:
        if completed := _completed_rollout(ctx):
            return completed
        harbor, harbor_env = uv_run(ctx.workspace, "harbor")
        eval_env = _load_eval_env(checkout)
        dedicated_tasks = ctx.config.get("path") or os.environ.get("EVOLVE_HARBOR_ROLLOUT_TASKS")
        manifest_path = checkout / "evaluator" / "splits.json"
        try:
            manifest = load_manifest(manifest_path)
        except RuntimeError:
            manifest = {}
        if dedicated_tasks and manifest.get("resolved"):
            raise SystemExit(
                "operators.rollout.path bypasses the frozen dataset split; remove it and use evaluator.dataset"
            )
        tasks = str(dedicated_tasks or eval_env.get("EVOLVE_HARBOR_TASKS") or "")
        agent = str(ctx.config.get("agent") or eval_env.get("EVOLVE_HARBOR_AGENT") or "")
        if not tasks:
            raise SystemExit(
                "harbor rollout requires evaluator.dataset, operators.rollout.path, or EVOLVE_HARBOR_ROLLOUT_TASKS"
            )
        if not agent:
            raise SystemExit("harbor rollout requires an agent in config or evaluator/eval.env")

        budget_tasks = _positive_int(ctx.config.get("budget_tasks"), 8)
        split_task_names: list[str] = []
        if not dedicated_tasks:
            split_name = str(ctx.config.get("split") or "train")
            if split_name != "train":
                raise SystemExit("harbor rollout may only consume the train split")
            try:
                split_task_names = _select_train_tasks(
                    manifest_path,
                    tasks,
                    budget_tasks,
                    ctx.config.get("task_names"),
                    sampling=str(ctx.config.get("task_sampling") or "head"),
                    sampling_key=f"{ctx.config.get('seed', 0)}:{ctx.genid}",
                )
            except Exception as exc:
                raise SystemExit(str(exc)) from exc
            budget_tasks = len(split_task_names)
        default_concurrent = _positive_int(eval_env.get("EVOLVE_HARBOR_N_CONCURRENT"), budget_tasks)
        n_concurrent = min(budget_tasks, _positive_int(ctx.config.get("n_concurrent"), default_concurrent))
        setup_timeout_multiplier = _float_value(
            ctx.config.get("agent_setup_timeout_multiplier"),
            _float_value(eval_env.get("EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER"), 1),
        )
        agent_timeout_multiplier = _float_value(
            ctx.config.get("agent_timeout_multiplier"),
            _float_value(eval_env.get("EVOLVE_HARBOR_AGENT_TIMEOUT_MULTIPLIER"), 1),
        )
        verifier_timeout_multiplier = _float_value(
            ctx.config.get("verifier_timeout_multiplier"),
            _float_value(eval_env.get("EVOLVE_HARBOR_VERIFIER_TIMEOUT_MULTIPLIER"), 1),
        )
        max_retries = _configured_max_retries(ctx.config, eval_env)
        field_limit = _positive_int(ctx.config.get("field_limit"), 2000)
        pass_threshold = _float_value(ctx.config.get("pass_threshold"), 1.0)
        jobs_root = _jobs_root(ctx)
        jobs_dir = jobs_root / f"gen-{ctx.genid}"
        _reset_directory(jobs_dir)

        base_command = [
            *harbor,
            "run",
            "-p",
            tasks,
            "--agent",
            agent,
            "--ae",
            f"EVOLVE_CANDIDATE_SOURCE={(checkout / 'target').resolve()}",
            "--n-attempts",
            "1",
            "--agent-setup-timeout-multiplier",
            str(max(setup_timeout_multiplier, 1)),
            "--agent-timeout-multiplier",
            str(max(agent_timeout_multiplier, 1)),
            "--verifier-timeout-multiplier",
            str(max(verifier_timeout_multiplier, 1)),
            "--max-retries",
            str(max_retries),
            "-y",
        ]
        environment = ctx.config.get("environment")
        if environment:
            base_command.extend(["--env", str(environment)])
        environment_kwargs = ctx.config.get("environment_kwargs")
        if isinstance(environment_kwargs, dict):
            for key in sorted(environment_kwargs):
                value = environment_kwargs[key]
                base_command.extend(["--environment-kwarg", f"{key}={json.dumps(value, separators=(',', ':'))}"])
        if os.environ.get("EVOLVE_LIVE_OUTPUT") != "1":
            base_command.append("-q")
        base_command.extend(["--ae", f"EVOLVE_CANDIDATE_SOURCE={(checkout / 'target').resolve()}"])
        configured_cache = eval_env.get("EVOLVE_UV_CACHE_DIR") or os.environ.get("EVOLVE_UV_CACHE_DIR")
        uv_cache = (
            Path(configured_cache).expanduser() if configured_cache else ctx.workspace / "runs" / "runtime" / "uv-cache"
        )
        uv_cache.mkdir(parents=True, exist_ok=True)
        mounts = [
            {
                "type": "bind",
                "source": str(uv_cache.resolve()),
                "target": "/opt/evolve/uv/cache",
            }
        ]
        uv_python = os.environ.get("EVOLVE_UV_PYTHON_INSTALL_DIR")
        if uv_python:
            uv_python_dir = Path(uv_python).expanduser().resolve()
            uv_python_dir.mkdir(parents=True, exist_ok=True)
            mounts.append(
                {
                    "type": "bind",
                    "source": str(uv_python_dir),
                    "target": "/installed-agent/uv-python",
                }
            )
        base_command.extend(
            [
                "--mounts",
                json.dumps(mounts),
            ]
        )
        _append_agent_env(base_command, checkout, ctx.config)
        base_command.extend(["--ae", "UV_CACHE_DIR=/opt/evolve/uv/cache"])
        if uv_python:
            base_command.extend(["--ae", "UV_PYTHON_INSTALL_DIR=/installed-agent/uv-python"])
        model = ctx.config.get("model") or eval_env.get("EVOLVE_HARBOR_MODEL") or os.environ.get("EVOLVE_HARBOR_MODEL")
        if not model and os.environ.get("OPENAI_MODEL"):
            model = f"openai/{os.environ['OPENAI_MODEL']}"
        if model:
            base_command.extend(["--model", str(model)])
        include_task = ctx.config.get("include_task_name")

        rollout_dir = ctx.run_dir / "rollout"
        initial_command = _batch_command(
            base_command,
            jobs_dir=jobs_dir,
            n_concurrent=n_concurrent,
            budget_tasks=budget_tasks,
            task_selectors=split_task_names,
            include_task=include_task,
        )
        returncode = _run_harbor(initial_command, checkout, rollout_dir / "harbor.log", harbor_env)
        cases = _with_missing_result_placeholders(
            collect_cases(
                jobs_dir,
                field_limit=field_limit,
                pass_threshold=pass_threshold,
                tasks_dir=Path(tasks) if Path(tasks).is_dir() else None,
                workspace=ctx.workspace,
                trajectory_archive_dir=rollout_dir / "trajectories",
            ),
            split_task_names,
        )
        if not cases:
            cases = [_batch_failure_case(rollout_dir / "harbor.log", returncode, field_limit)]

        _write_json(rollout_dir / "cases.json", cases)
        require_rollout_cases(cases, returncode=returncode, harbor_log=rollout_dir / "harbor.log")

        rewards = [case["reward"] for case in cases if isinstance(case.get("reward"), (int, float))]
        counts = {name: sum(case["outcome"] == name for case in cases) for name in _OUTCOME_ORDER}
        infra_tasks = [
            str(case.get("task_name") or case.get("trial_name") or "unknown")
            for case in cases
            if case.get("outcome") in {"infra_error", "incomplete"}
        ]
        summary = {
            "variant": "harbor",
            "split": "dedicated" if dedicated_tasks else "train",
            "harbor_returncode": returncode,
            "tasks_requested": budget_tasks,
            "tasks_observed": len(cases),
            "passed": counts["passed"],
            "failed": counts["failed"],
            "agent_errors": counts["agent_error"],
            "infra_errors": counts["infra_error"] + counts["incomplete"],
            "infra_tasks": infra_tasks,
            "mean_observed_reward": round(sum(rewards) / len(rewards), 6) if rewards else None,
            "jobs_dir": str(jobs_dir),
        }
        return RolloutResult(
            summary=summary,
            artifacts=[
                "rollout/harbor.log",
                "rollout/cases.json",
                f"harbor-jobs:{jobs_dir}",
            ],
        )


if __name__ == "__main__":
    sdk.main(HarborRollout, validate_config=validate_config)
