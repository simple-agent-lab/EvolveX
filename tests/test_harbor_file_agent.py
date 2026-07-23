import asyncio
import importlib.util
import json
import shlex
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "templates" / "workspace" / "evolve_harbor_agent" / "__init__.py"


def _load(monkeypatch):
    harbor = types.ModuleType("harbor")
    agents = types.ModuleType("harbor.agents")
    installed = types.ModuleType("harbor.agents.installed")
    mini = types.ModuleType("harbor.agents.installed.mini_swe_agent")

    class MiniSweAgent:
        async def run(self, instruction, environment, context):
            del context
            await self.exec_as_agent(environment, command="setup", env={"ROLE": "agent"})
            await self.exec_as_agent(
                environment,
                command=(
                    "source-env; mini-swe-agent --yolo --model=openai/test "
                    f"--task={shlex.quote(instruction)} --output=/logs/trajectory.json "
                    "-c mini -c model.model_class=litellm_response "
                    "-c model.model_kwargs.reasoning.effort=xhigh "
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
    spec = importlib.util.spec_from_file_location("evolve_harbor_agent_under_test", ADAPTER)
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
    assert model_kwargs["include"] == ["reasoning.encrypted_content"]
    assert model_kwargs["prompt_cache_key"].startswith("evolve-")
    assert json.loads(model_kwargs["extra_headers"]["extra"]) == {
        "session_id": model_kwargs["prompt_cache_key"]
    }
    assert "store" not in model_kwargs
    assert "unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy;" in runtime_command
    assert environment.envs[-1] == {"ROLE": "agent"}
