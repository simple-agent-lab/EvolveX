from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ADAPTER = (
    Path(__file__).resolve().parents[1] / "templates" / "workspace" / "evolve_harbor_adapter" / "modelhub_codex.py"
)


class FakeCodex:
    def __init__(self, env: dict[str, str]) -> None:
        self.env = env

    def _get_env(self, name: str) -> str | None:
        return self.env.get(name)

    def build_cli_flags(self) -> str:
        return "-c model_reasoning_effort=xhigh"


def _load_adapter(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    modules = {
        "harbor": types.ModuleType("harbor"),
        "harbor.agents": types.ModuleType("harbor.agents"),
        "harbor.agents.installed": types.ModuleType("harbor.agents.installed"),
        "harbor.agents.installed.codex": types.ModuleType("harbor.agents.installed.codex"),
        "harbor.environments": types.ModuleType("harbor.environments"),
        "harbor.environments.base": types.ModuleType("harbor.environments.base"),
        "harbor.models": types.ModuleType("harbor.models"),
        "harbor.models.agent": types.ModuleType("harbor.models.agent"),
        "harbor.models.agent.context": types.ModuleType("harbor.models.agent.context"),
    }
    modules["harbor.agents.installed.codex"].Codex = FakeCodex
    modules["harbor.environments.base"].BaseEnvironment = object
    modules["harbor.models.agent.context"].AgentContext = object
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("modelhub_codex_adapter_test", ADAPTER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_modelhub_codex_flags_use_bridge_provider_without_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_adapter(monkeypatch)
    secret = "secret-value-must-not-appear"
    agent = module.ModelHubCodexAgent({"OPENAI_BASE_URL": "https://hub.example/v1", "OPENAI_API_KEY": secret})

    flags = agent.build_cli_flags()

    assert "model_reasoning_effort=xhigh" in flags
    assert 'model_provider="my_model_hub"' in flags
    assert "https://hub.example/v1" in flags
    assert 'env_key="OPENAI_API_KEY"' in flags
    assert "env_http_headers" not in flags
    assert "supports_websockets=false" in flags
    assert secret not in flags


@pytest.mark.parametrize("missing", ["OPENAI_BASE_URL", "OPENAI_API_KEY"])
def test_modelhub_codex_requires_runtime_credentials(missing: str, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_adapter(monkeypatch)
    env = {"OPENAI_BASE_URL": "https://hub.example/v1", "OPENAI_API_KEY": "secret"}
    del env[missing]
    agent = module.ModelHubCodexAgent(env)

    with pytest.raises(RuntimeError, match=missing):
        agent.build_cli_flags()
