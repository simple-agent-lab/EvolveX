from __future__ import annotations

from library._shared.config import mapping, string

RUNNER_KEYS = frozenset(
    {
        "runner",
        "command",
        "agent",
        "model",
        "environment",
        "environment_kwargs",
        "image",
        "workdir",
        "agent_kwargs",
        "agent_env",
        "agent_pythonpath",
        "jobs_dir",
    }
)

_STRING_KEYS = (
    "command",
    "agent",
    "model",
    "environment",
    "image",
    "workdir",
    "agent_pythonpath",
    "jobs_dir",
)
_MAPPING_KEYS = ("environment_kwargs", "agent_kwargs", "agent_env")


def normalize_runner_config(config: dict[str, object]) -> dict[str, object]:
    runner = string(config, "runner", "local")
    if runner not in {"local", "harbor"}:
        raise ValueError("runner must be 'local' or 'harbor'")
    normalized: dict[str, object] = {"runner": runner}
    for key in _STRING_KEYS:
        if key in config:
            normalized[key] = string(config, key, "")
    for key in _MAPPING_KEYS:
        if key in config:
            normalized[key] = mapping(config, key, {})
    return normalized
