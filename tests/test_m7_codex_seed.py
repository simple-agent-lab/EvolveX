from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from conftest import run_evolve


class FakeCliFlag:
    def __init__(self, kwarg: str, **kwargs: Any) -> None:
        self.kwarg = kwarg
        self.kwargs = kwargs


class FakeCodex:
    CLI_FLAGS: list[FakeCliFlag] = []

    def __init__(self, logs_dir: Path, model_name: str | None = None, **kwargs: Any) -> None:
        self.logs_dir = logs_dir
        self.model_name = model_name
        self.kwargs = kwargs
        self.base_setup_called = False
        self.instructions: list[str] = []

    def _get_env(self, name: str) -> str | None:
        return os.environ.get(name)

    def _resolve_auth_json_path(self) -> None:
        return None

    async def setup(self, environment: object) -> None:
        self.base_setup_called = True

    async def run(self, instruction: str, environment: object, context: object) -> None:
        del environment, context
        self.instructions.append(instruction)


class FakeBaseEnvironment:
    pass


class RecordingEnvironment:
    def __init__(self) -> None:
        self.uploads: list[tuple[Path, str]] = []

    async def upload_dir(self, source_dir: Path, target_dir: str) -> None:
        self.uploads.append((source_dir, target_dir))


def _install_fake_harbor(monkeypatch) -> None:
    modules = {
        "harbor": ModuleType("harbor"),
        "harbor.agents": ModuleType("harbor.agents"),
        "harbor.agents.installed": ModuleType("harbor.agents.installed"),
        "harbor.agents.installed.base": ModuleType("harbor.agents.installed.base"),
        "harbor.agents.installed.codex": ModuleType("harbor.agents.installed.codex"),
        "harbor.environments": ModuleType("harbor.environments"),
        "harbor.environments.base": ModuleType("harbor.environments.base"),
    }
    modules["harbor.agents.installed.base"].CliFlag = FakeCliFlag
    modules["harbor.agents.installed.codex"].Codex = FakeCodex
    modules["harbor.environments.base"].BaseEnvironment = FakeBaseEnvironment
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def _load_target_agent(path: Path):
    spec = importlib.util.spec_from_file_location("evolve_test_builtin_codex", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_builtin_codex_wrapper_injects_skills_and_opt_in_compaction(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "experiment"
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "aevolve",
        "--seed",
        "builtin-codex",
        env={"EVOLVE_HOME": str(tmp_path / "home")},
    )
    assert result.returncode == 0, result.stderr
    _install_fake_harbor(monkeypatch)
    module = _load_target_agent(workspace / "target" / "agent.py")

    agent = module.HarborAgent(logs_dir=tmp_path / "logs")
    assert agent.model_name == "gpt-5.4"
    assert agent.kwargs["skills_dir"] == "/tmp/evolve-target-skills"
    assert "auto_compact_token_limit" not in agent.kwargs
    assert {flag.kwarg for flag in agent.CLI_FLAGS} >= {
        "auto_compact_token_limit",
        "auto_compact_token_limit_scope",
        "tool_output_token_limit",
    }

    environment = RecordingEnvironment()
    asyncio.run(agent.setup(environment))
    assert agent.base_setup_called is True
    assert environment.uploads == [
        (workspace / "target" / "skills", "/tmp/evolve-target-skills"),
    ]

    assert "_resolve_auth_json_path" not in module.HarborAgent.__dict__
    assert agent._resolve_auth_json_path() is None

    config_path = workspace / "target" / "codex.toml"
    config_path.write_text(config_path.read_text().replace("override_defaults = false", "override_defaults = true"))
    compacting_agent = module.HarborAgent(logs_dir=tmp_path / "logs-2")
    assert compacting_agent.kwargs["auto_compact_token_limit"] == 100000
    assert compacting_agent.kwargs["auto_compact_token_limit_scope"] == "total"
    assert compacting_agent.kwargs["tool_output_token_limit"] == 12000


@pytest.mark.parametrize(
    ("smoke_mode", "expected"),
    [
        ("model", "Reply with exactly OK. Do not use tools."),
        ("install", "Fix the benchmark bug."),
        (None, "Fix the benchmark bug."),
    ],
)
def test_builtin_codex_model_smoke_replaces_only_the_benchmark_instruction(
    tmp_path: Path,
    monkeypatch,
    smoke_mode: str | None,
    expected: str,
) -> None:
    workspace = tmp_path / "experiment"
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "aevolve",
        "--seed",
        "builtin-codex",
        env={"EVOLVE_HOME": str(tmp_path / "home")},
    )
    assert result.returncode == 0, result.stderr
    _install_fake_harbor(monkeypatch)
    module = _load_target_agent(workspace / "target" / "agent.py")
    if smoke_mode is None:
        monkeypatch.delenv("EVOLVE_CANDIDATE_SMOKE_MODE", raising=False)
    else:
        monkeypatch.setenv("EVOLVE_CANDIDATE_SMOKE_MODE", smoke_mode)
    agent = module.HarborAgent(logs_dir=tmp_path / "logs")

    asyncio.run(agent.run("Fix the benchmark bug.", object(), object()))

    assert agent.instructions == [expected]
