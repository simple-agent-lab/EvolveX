import asyncio
import importlib.util
import json
import shlex
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "src" / "evolve" / "integrations" / "harbor" / "miniswe_task_file.py"
FILE_TASK_AGENT = "evolve.integrations.harbor.miniswe_task_file:FileTaskMiniSweAgent"


def _load(monkeypatch, max_output_tokens: int | str | None = None):
    harbor = types.ModuleType("harbor")
    agents = types.ModuleType("harbor.agents")
    installed = types.ModuleType("harbor.agents.installed")
    mini = types.ModuleType("harbor.agents.installed.mini_swe_agent")

    class MiniSweAgent:
        async def run(self, instruction, environment, context):
            await self.exec_as_agent(environment, command="setup", env={"ROLE": "agent"})
            output_budget = max_output_tokens
            if output_budget is None:
                output_budget = getattr(context, "max_output_tokens", None)
            output_budget_config = (
                f" -c model.model_kwargs.max_output_tokens={output_budget}"
                if output_budget is not None
                else ""
            )
            await self.exec_as_agent(
                environment,
                command=(
                    "source-env; mini-swe-agent --yolo --model=openai/test "
                    f"--task={shlex.quote(instruction)} --output=/logs/trajectory.json "
                    "-c mini -c model.model_class=litellm_response "
                    "-c model.model_kwargs.reasoning.effort=xhigh "
                    f"{output_budget_config} "
                    "--exit-immediately 2>&1 | tee /logs/agent.txt"
                ),
                env={"ROLE": "agent"},
            )

        async def exec_as_agent(self, environment, command, env=None, **kwargs):
            del kwargs
            environment.commands.append(command)
            environment.envs.append(env or {})

    mini.MiniSweAgent = MiniSweAgent
    monkeypatch.setitem(sys.modules, "harbor", harbor)
    monkeypatch.setitem(sys.modules, "harbor.agents", agents)
    monkeypatch.setitem(sys.modules, "harbor.agents.installed", installed)
    monkeypatch.setitem(sys.modules, "harbor.agents.installed.mini_swe_agent", mini)
    spec = importlib.util.spec_from_file_location("evolve.integrations.harbor.miniswe_task_file", ADAPTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Environment:
    def __init__(self):
        self.commands = []
        self.envs = []
        self.uploads = []

    async def upload_file(self, source, destination):
        self.uploads.append((destination, Path(source).read_text()))


def test_file_task_agent_externalizes_large_miniswe_instruction(monkeypatch) -> None:
    module = _load(monkeypatch)
    environment = Environment()
    payload = "evidence\n" + "x" * 200_000

    asyncio.run(module.FileTaskMiniSweAgent().run(payload, environment, object()))

    runtime_command = environment.commands[-1]
    uploaded = dict(environment.uploads)
    assert environment.commands[0] == "setup"
    assert payload not in runtime_command
    assert uploaded[module.TASK_PATH] == payload
    assert "runpy.run_path" in uploaded[module.SHIM_PATH]
    assert module.TASK_PATH in runtime_command
    assert module.SHIM_PATH in runtime_command
    assert "--output=/logs/trajectory.json" in runtime_command
    assert "model.model_class=litellm_response" in runtime_command
    assert "model.model_kwargs.reasoning.effort=xhigh" in runtime_command
    assert module.RESPONSES_CONFIG_PATH in runtime_command
    responses_config = json.loads(uploaded[module.RESPONSES_CONFIG_PATH])
    model_kwargs = responses_config["model"]["model_kwargs"]
    assert model_kwargs["max_output_tokens"] == 64_000
    assert model_kwargs["include"] == ["reasoning.encrypted_content"]
    assert model_kwargs["prompt_cache_key"].startswith("evolve-")
    assert json.loads(model_kwargs["extra_headers"]["extra"]) == {
        "session_id": model_kwargs["prompt_cache_key"]
    }
    assert "store" not in model_kwargs
    assert "unset HTTP_PROXY" not in runtime_command
    assert environment.envs[-1] == {"ROLE": "agent"}


def test_file_task_agent_preserves_explicit_output_budget(monkeypatch) -> None:
    module = _load(monkeypatch, max_output_tokens=12_345)
    environment = Environment()

    asyncio.run(module.FileTaskMiniSweAgent().run("Fix the constant.", environment, object()))

    uploaded = dict(environment.uploads)
    responses_config = json.loads(uploaded[module.RESPONSES_CONFIG_PATH])
    assert "max_output_tokens" not in responses_config["model"]["model_kwargs"]
    assert "model.model_kwargs.max_output_tokens=12345" in environment.commands[-1]


def test_file_task_agent_defaults_for_malformed_output_budget_override(monkeypatch) -> None:
    for output_budget in ("not-an-integer", "12345suffix"):
        module = _load(monkeypatch, max_output_tokens=output_budget)
        environment = Environment()

        asyncio.run(module.FileTaskMiniSweAgent().run("Fix the constant.", environment, object()))

        uploaded = dict(environment.uploads)
        responses_config = json.loads(uploaded[module.RESPONSES_CONFIG_PATH])
        assert responses_config["model"]["model_kwargs"]["max_output_tokens"] == 64_000
