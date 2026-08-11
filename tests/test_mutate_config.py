from __future__ import annotations

import pytest

from evolve.frozen.config import ConfigError
from library._shared.gepa import normalize_components
from library.mutate._config import RUNNER_CONFIG


def test_runner_config_preserves_supported_values() -> None:
    raw: dict[str, object] = {
        "runner": "harbor",
        "command": "printf accepted",
        "agent": "provider.Agent",
        "model": "provider/model",
        "environment": "provider.Environment",
        "environment_kwargs": {"network": "host"},
        "image": "registry/image:tag",
        "workdir": "/app/task",
        "agent_kwargs": {"reasoning": "high"},
        "agent_env": {"TOKEN": "configured"},
        "agent_pythonpath": "/app/python",
        "jobs_dir": "runs/jobs",
    }

    assert RUNNER_CONFIG.normalize(raw) == raw


def test_runner_config_defaults_and_rejects_unknown_runner() -> None:
    assert RUNNER_CONFIG.normalize({}) == {"runner": "local"}

    with pytest.raises(ConfigError, match="runner"):
        RUNNER_CONFIG.normalize({"runner": "remote"})


def test_runner_config_accepts_arbitrary_json_mappings() -> None:
    assert RUNNER_CONFIG.normalize(
        {
            "agent_kwargs": {"nested": {"count": 2}},
            "agent_env": {"TOKEN": None},
            "environment_kwargs": {"flags": [True, "safe"]},
        }
    ) == {
        "runner": "local",
        "agent_kwargs": {"nested": {"count": 2}},
        "agent_env": {"TOKEN": None},
        "environment_kwargs": {"flags": [True, "safe"]},
    }


def test_component_normalizer_converts_scalar_paths_to_lists() -> None:
    assert normalize_components({"prompt": "target/prompt.md"}) == {"prompt": ["target/prompt.md"]}


def test_component_normalizer_rejects_unsafe_paths_without_echoing_values() -> None:
    rejected = "../PRIVATE_TOKEN"

    with pytest.raises(ValueError) as caught:
        normalize_components({"prompt": rejected})

    assert "checkout-relative" in str(caught.value)
    assert rejected not in str(caught.value)
