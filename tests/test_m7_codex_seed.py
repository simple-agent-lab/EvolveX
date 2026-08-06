from __future__ import annotations

import asyncio
import importlib.util
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
        self.agent_commands: list[str] = []

    def _get_env(self, _name: str) -> str | None:
        return None

    def _build_register_skills_command(self) -> str | None:
        return "register-base-skills"

    async def exec_as_agent(
        self,
        environment: object,
        command: str,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout_sec: int | None = None,
    ) -> str:
        del environment, env, cwd, timeout_sec
        self.agent_commands.append(command)
        return command

    async def setup(self, environment: object) -> None:
        self.base_setup_called = True


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
    assert agent.agent_commands == [
        "mkdir -p /tmp/evolve-target-skills "
        "/tmp/evolve-target-marketplace/.agents /tmp/evolve-target-marketplace/plugins"
    ]
    assert environment.uploads == [
        (workspace / "target" / "skills", "/tmp/evolve-target-skills"),
        (workspace / "target" / ".agents", "/tmp/evolve-target-marketplace/.agents"),
        (workspace / "target" / "plugins", "/tmp/evolve-target-marketplace/plugins"),
    ]

    registration = agent._build_register_skills_command()
    assert registration is not None
    assert "register-base-skills" in registration
    assert registration.count(". ~/.nvm/nvm.sh") == 2
    assert "codex plugin marketplace add /tmp/evolve-target-marketplace" in registration
    assert "codex plugin add evolve-target@evolve-target" in registration
    rewritten = asyncio.run(agent.exec_as_agent(environment, "codex exec --json -- task"))
    assert rewritten == "codex exec --dangerously-bypass-hook-trust --json -- task"
    unchanged = asyncio.run(agent.exec_as_agent(environment, "codex plugin list"))
    assert unchanged == "codex plugin list"

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    auth_path = tmp_path / "home" / ".codex" / "auth.json"
    with pytest.raises(ValueError, match="auth.json does not exist"):
        agent._resolve_auth_json_path()
    auth_path.parent.mkdir(parents=True)
    auth_path.write_text("{}\n")
    assert agent._resolve_auth_json_path() == auth_path
    custom_home = tmp_path / "custom-codex-home"
    custom_home.mkdir()
    (custom_home / "auth.json").write_text("{}\n")
    agent._get_env = lambda name: str(custom_home) if name == "CODEX_HOME" else None
    assert agent._resolve_auth_json_path() == custom_home / "auth.json"

    config_path = workspace / "target" / "codex.toml"
    config_path.write_text(config_path.read_text().replace("override_defaults = false", "override_defaults = true"))
    compacting_agent = module.HarborAgent(logs_dir=tmp_path / "logs-2")
    assert compacting_agent.kwargs["auto_compact_token_limit"] == 100000
    assert compacting_agent.kwargs["auto_compact_token_limit_scope"] == "total"
    assert compacting_agent.kwargs["tool_output_token_limit"] == 12000


def test_builtin_codex_seed_contains_valid_plugin_layout() -> None:
    root = Path(__file__).resolve().parents[1] / "seeds" / "codex"
    marketplace = __import__("json").loads((root / ".agents" / "plugins" / "marketplace.json").read_text())
    plugin = root / "plugins" / "evolve-target"
    manifest = __import__("json").loads((plugin / ".codex-plugin" / "plugin.json").read_text())
    hooks = __import__("json").loads((plugin / "hooks" / "hooks.json").read_text())

    assert marketplace["name"] == "evolve-target"
    assert marketplace["plugins"][0]["source"]["path"] == "./plugins/evolve-target"
    assert manifest["name"] == plugin.name
    assert "hooks" not in manifest
    assert hooks["hooks"]["SessionStart"][0]["hooks"][0]["type"] == "command"
    assert (plugin / "hooks" / "session_start.py").is_file()
    assert "EVOLVE_PLUGIN_SESSION_CONTEXT_V1" in (plugin / "context.md").read_text()


def test_paper_poster_codex_seed_uses_cli_default_unless_model_is_explicit(tmp_path: Path, monkeypatch) -> None:
    _install_fake_harbor(monkeypatch)
    module = _load_target_agent(
        Path(__file__).parents[1] / "evals" / "skills" / "make-paper-poster" / "seed" / "agent.py"
    )

    default_agent = module.HarborAgent(logs_dir=tmp_path / "default")
    assert default_agent.model_name is None
    command = asyncio.run(
        default_agent.exec_as_agent(
            RecordingEnvironment(),
            f"codex exec --model {module.DEFAULT_MODEL_SENTINEL} --json -- task",
        )
    )
    assert "--model" not in command

    pinned_agent = module.HarborAgent(logs_dir=tmp_path / "pinned", model_name="gpt-pinned")
    assert pinned_agent.model_name == "gpt-pinned"


def test_builtin_codex_wrapper_uploads_skills_from_exact_candidate_source(tmp_path: Path, monkeypatch) -> None:
    _install_fake_harbor(monkeypatch)
    module = _load_target_agent(Path(__file__).parents[1] / "seeds" / "codex" / "agent.py")
    candidate = tmp_path / "candidate"
    (candidate / "skills" / "example").mkdir(parents=True)
    (candidate / "skills" / "example" / "SKILL.md").write_text("candidate\n")
    agent = module.HarborAgent(logs_dir=tmp_path / "logs")
    agent._get_env = lambda name: str(candidate) if name == "EVOLVE_CANDIDATE_SOURCE" else None
    environment = RecordingEnvironment()

    asyncio.run(agent.setup(environment))

    assert environment.uploads == [(candidate / "skills", "/tmp/evolve-target-skills")]
