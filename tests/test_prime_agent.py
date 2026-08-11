from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "src" / "evolve" / "integrations" / "harbor" / "prime_agent.py"


class FakeBaseInstalledAgent:
    def __init__(self, *args, **kwargs) -> None:
        del args
        self.logs_dir = Path(kwargs.get("logs_dir") or ".")
        self.model_name = kwargs.get("model_name")
        self._extra_env = dict(kwargs.get("extra_env") or {})
        self.agent_commands: list[str] = []
        self.root_commands: list[str] = []
        self.agent_envs: list[dict[str, str]] = []

    def _get_env(self, name: str) -> str | None:
        return self._extra_env.get(name)

    def build_cli_flags(self) -> str:
        return ""

    async def exec_as_agent(self, environment, command: str, env: dict[str, str] | None = None) -> None:
        del environment
        self.agent_commands.append(command)
        self.agent_envs.append(dict(env or {}))

    async def exec_as_root(self, environment, command: str, env: dict[str, str] | None = None) -> None:
        del environment, env
        self.root_commands.append(command)


class FakeCliFlag:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs


class FakeEnvironment:
    def __init__(self) -> None:
        self.uploads: list[tuple[Path, str]] = []
        self.downloads: list[tuple[str, Path]] = []

    async def upload_file(self, source, target: str) -> None:
        self.uploads.append((Path(source), target))

    async def download_dir(self, source: str, target) -> None:
        self.downloads.append((source, Path(target)))


def _load(monkeypatch):
    base = ModuleType("harbor.agents.installed.base")
    base.BaseInstalledAgent = FakeBaseInstalledAgent
    base.CliFlag = FakeCliFlag
    base.with_prompt_template = lambda fn: fn

    node_install = ModuleType("harbor.agents.installed.node_install")
    node_install.nvm_node_install_snippet = lambda: "install-node"

    context = ModuleType("harbor.models.agent.context")
    context.AgentContext = object

    modules = {
        "harbor": ModuleType("harbor"),
        "harbor.agents": ModuleType("harbor.agents"),
        "harbor.agents.installed": ModuleType("harbor.agents.installed"),
        "harbor.agents.installed.base": base,
        "harbor.agents.installed.node_install": node_install,
        "harbor.models": ModuleType("harbor.models"),
        "harbor.models.agent": ModuleType("harbor.models.agent"),
        "harbor.models.agent.context": context,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location("evolve.integrations.harbor.prime_agent", ADAPTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _run(agent, environment) -> None:
    await agent.run("solve it", environment, context=None)


@pytest.mark.parametrize(
    ("auto_refine", "expected", "forbidden"),
    [(False, "--no-session", "--session-dir"), (True, "--session-dir", "--no-session")],
)
def test_session_is_kept_only_when_refinement_is_expected(monkeypatch, auto_refine, expected, forbidden) -> None:
    """Prime gates auto-refine on a session-local harness dir, so `--no-session`
    disables refinement structurally regardless of the autoRefine settings."""
    module = _load(monkeypatch)
    agent = module.PrimeAgent(model_name="openai/gpt", auto_refine=auto_refine)
    environment = FakeEnvironment()

    import asyncio

    asyncio.run(_run(agent, environment))

    run_command = agent.agent_commands[-1]
    assert expected in run_command
    assert forbidden not in run_command


def test_refine_thresholds_are_written_into_settings(monkeypatch) -> None:
    """Prime ships turnInterval=25 and a 20 minute cooldown, which never fire on
    a short episode; the thresholds must be explicit to be reproducible."""
    module = _load(monkeypatch)
    agent = module.PrimeAgent(
        model_name="openai/gpt",
        auto_refine=True,
        refine_turn_interval=1,
        refine_cooldown_ms=0,
    )

    settings = agent._settings()["autoRefine"]

    assert settings == {"enabled": True, "compact": True, "turnInterval": 1, "cooldownMs": 0}


def test_settings_omit_thresholds_when_unset(monkeypatch) -> None:
    module = _load(monkeypatch)
    agent = module.PrimeAgent(model_name="openai/gpt")

    assert agent._settings()["autoRefine"] == {"enabled": False, "compact": False}


def test_version_command_captures_stderr(monkeypatch) -> None:
    """prime-agent prints its version on stderr; without the redirect Harbor
    records the agent version as "unknown"."""
    module = _load(monkeypatch)
    agent = module.PrimeAgent(model_name="openai/gpt")

    assert agent.get_version_command().endswith("prime-agent --version 2>&1")


def test_runtime_prefix_skips_network_install(monkeypatch) -> None:
    module = _load(monkeypatch)
    agent = module.PrimeAgent(model_name="openai/gpt", runtime_prefix="/opt/prime-runtime")
    environment = FakeEnvironment()

    import asyncio

    asyncio.run(agent.install(environment))

    assert agent.root_commands == []
    install_command = agent.agent_commands[-1]
    assert "install-node" not in install_command
    assert "/opt/prime-runtime/bin/prime-agent" in install_command
    # The kernel venv needs a writable copy: Prime writes a bootstrap lock next
    # to it, which fails on a read-only mount.
    assert "cp -a /opt/prime-runtime/kernel-venv" in install_command


def test_network_install_used_without_runtime_prefix(monkeypatch) -> None:
    module = _load(monkeypatch)
    agent = module.PrimeAgent(model_name="openai/gpt")
    environment = FakeEnvironment()

    import asyncio

    asyncio.run(agent.install(environment))

    assert any("apt-get" in command for command in agent.root_commands)
    assert "install-node" in agent.agent_commands[-1]


def test_harness_state_is_uploaded_and_agent_dir_exported(monkeypatch, tmp_path) -> None:
    module = _load(monkeypatch)
    harness = tmp_path / "harness_state.json"
    harness.write_text(json.dumps({"schema": 1, "entries": {}}))
    agent = module.PrimeAgent(
        model_name="openai/gpt",
        harness_state_path=harness,
        logs_dir=tmp_path / "logs",
    )
    environment = FakeEnvironment()

    import asyncio

    asyncio.run(_run(agent, environment))

    assert (harness, "/tmp/prime-agent-dir/harness/harness_state.json") in environment.uploads
    assert environment.downloads == [("/tmp/prime-agent-dir", tmp_path / "logs" / "prime-agent-dir")]


def test_missing_harness_state_fails_closed(monkeypatch, tmp_path) -> None:
    module = _load(monkeypatch)
    agent = module.PrimeAgent(model_name="openai/gpt", harness_state_path=tmp_path / "absent.json")

    import asyncio

    with pytest.raises(module.PrimeRuntimeMissingError, match="harness_state_path"):
        asyncio.run(_run(agent, FakeEnvironment()))


def test_usage_is_summed_from_message_end_events(monkeypatch, tmp_path) -> None:
    module = _load(monkeypatch)
    logs = tmp_path / "logs"
    logs.mkdir()
    events = [
        {"type": "message_start", "message": {"role": "assistant"}},
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "usage": {"input": 100, "output": 20, "cacheRead": 5, "cost": {"total": 0.5}},
            },
        },
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "usage": {"input": 40, "output": 10, "cacheRead": 1, "cost": {"total": 0.25}},
            },
        },
        {"type": "message_end", "message": {"role": "toolResult", "usage": {"input": 999}}},
        "not json",
    ]
    (logs / "prime-agent.jsonl").write_text(
        "\n".join(event if isinstance(event, str) else json.dumps(event) for event in events)
    )
    agent = module.PrimeAgent(model_name="openai/gpt", logs_dir=logs)

    class Context:
        pass

    context = Context()
    agent.populate_context_post_run(context)

    assert context.n_input_tokens == 146
    assert context.n_output_tokens == 30
    assert context.n_cache_tokens == 6
    assert context.cost_usd == pytest.approx(0.75)


def test_model_name_must_carry_a_provider(monkeypatch) -> None:
    module = _load(monkeypatch)
    agent = module.PrimeAgent(model_name="gpt-without-provider")

    import asyncio

    with pytest.raises(ValueError, match="provider/model_name"):
        asyncio.run(_run(agent, FakeEnvironment()))
