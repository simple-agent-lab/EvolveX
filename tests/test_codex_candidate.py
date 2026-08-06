from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "src" / "evolve" / "integrations" / "harbor" / "codex_candidate.py"


class FakeCodex:
    def __init__(self, *args, **kwargs) -> None:
        del args
        self._extra_env = dict(kwargs.get("extra_env") or {})

    def _get_env(self, name: str) -> str | None:
        return self._extra_env.get(name) or os.environ.get(name)

    def build_cli_flags(self) -> str:
        return ""


def _load(monkeypatch):
    modules = {
        "harbor": ModuleType("harbor"),
        "harbor.agents": ModuleType("harbor.agents"),
        "harbor.agents.installed": ModuleType("harbor.agents.installed"),
        "harbor.agents.installed.codex": ModuleType("harbor.agents.installed.codex"),
    }
    modules["harbor.agents.installed.codex"].Codex = FakeCodex
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("evolve.integrations.harbor.codex_candidate", ADAPTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_responses_codex_agent_configures_api_provider(monkeypatch) -> None:
    module = _load(monkeypatch)
    agent = module.ResponsesCodexAgent(
        extra_env={
            "OPENAI_BASE_URL": "http://bridge.example/v1",
            "OPENAI_API_KEY": "test-key",
        }
    )

    flags = agent.build_cli_flags()

    assert 'model_provider="evolve_http"' in flags
    assert 'forced_login_method="api"' in flags
    assert 'model_providers.evolve_http.base_url="http://bridge.example/v1"' in flags
    assert 'model_providers.evolve_http.wire_api="responses"' in flags
    assert 'model_providers.evolve_http.env_http_headers={"api-key"="OPENAI_API_KEY"}' in flags
    assert "model_providers.evolve_http.supports_websockets=false" in flags


@pytest.mark.parametrize(
    ("extra_env", "message"),
    [
        ({"OPENAI_API_KEY": "test-key"}, "OPENAI_BASE_URL or OPENAI_API_BASE"),
        ({"OPENAI_BASE_URL": "http://bridge.example/v1"}, "OPENAI_API_KEY"),
    ],
)
def test_responses_codex_agent_requires_endpoint_and_key(monkeypatch, extra_env, message) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    module = _load(monkeypatch)
    with pytest.raises(ValueError, match=message):
        module.ResponsesCodexAgent(extra_env=extra_env).build_cli_flags()
