"""Validate Harbor rollout operator configuration."""

from __future__ import annotations

import math

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
