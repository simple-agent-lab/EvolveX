import asyncio
import importlib.util
import os
import sys
import types
from pathlib import Path


def _install_fake_harbor(monkeypatch):
    root = types.ModuleType("harbor")
    agents = types.ModuleType("harbor.agents")
    installed = types.ModuleType("harbor.agents.installed")
    mini = types.ModuleType("harbor.agents.installed.mini_swe_agent")

    class MiniSweAgent:
        def __init__(self, *args, **kwargs) -> None:
            self.model_name = kwargs.get("model_name", "openai/test-model")
            self.mcp_servers = []
            self._mini_swe_agent_trajectory_path = "/logs/agent/mini-swe-agent.trajectory.json"

        def _get_env(self, name: str):
            return {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_BASE_URL": "https://llm.example/v1",
                "EVOLVE_INSTALL_HTTP_PROXY": "http://proxy.example:8118",
            }.get(name) or os.environ.get(name)

        async def exec_as_agent(self, environment, command: str, env=None):
            environment.commands.append(command)
            environment.envs.append(env or {})

        async def exec_as_root(self, environment, command: str, env=None):
            environment.commands.append(command)
            environment.envs.append(env or {})

    mini.MiniSweAgent = MiniSweAgent
    monkeypatch.setitem(sys.modules, "harbor", root)
    monkeypatch.setitem(sys.modules, "harbor.agents", agents)
    monkeypatch.setitem(sys.modules, "harbor.agents.installed", installed)
    monkeypatch.setitem(sys.modules, "harbor.agents.installed.mini_swe_agent", mini)
    return MiniSweAgent


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("target.harbor_agent", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_miniswe_wrapper_subclasses_harbor_miniswe_and_installs_candidate_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base = _install_fake_harbor(monkeypatch)
    target = tmp_path / "target"
    target.mkdir()
    (target / "pyproject.toml").write_text("[project]\nname = 'mini-swe-agent'\nversion = '0.test'\n")
    (target / "src" / "minisweagent").mkdir(parents=True)
    wrapper = target / "harbor_agent.py"
    wrapper.write_text(Path("templates/target/harbor/miniswe_source_agent.py").read_text())
    module = _load(wrapper)

    class Environment:
        def __init__(self) -> None:
            self.uploads = []
            self.commands = []
            self.envs = []

        async def upload_dir(self, source_dir, target_dir):
            self.uploads.append((Path(source_dir), target_dir))

        async def upload_file(self, source_path, target_path):
            self.uploads.append((Path(source_path), target_path))

    environment = Environment()
    host_uv = tmp_path / "uv"
    host_uv.write_text("uv")
    monkeypatch.setenv("EVOLVE_UV_BINARY", str(host_uv))
    agent = module.MiniSweSourceAgent()
    asyncio.run(agent.install(environment))

    assert issubclass(module.MiniSweSourceAgent, base)
    assert environment.uploads == [(target.resolve(), "/installed-agent/miniswe-source"), (host_uv, "/tmp/evolve-uv")]
    joined = "\n".join(environment.commands)
    assert "apt-get install -y curl build-essential git python3" in joined
    assert 'cp /tmp/evolve-uv "$HOME/.local/bin/uv"' in joined
    assert '"$HOME/.local/bin/uv" --version' in joined
    assert "rm -f \"$HOME/.local/bin/uv\"" in joined
    assert "uv tool install" not in joined
    assert "mini-swe-agent --" not in joined
    assert "curl -LsSf https://astral.sh/uv/0.7.13/install.sh" in joined
    assert "uv run --project /installed-agent/miniswe-source python -c" in joined
    assert "import minisweagent" in joined
    assert environment.envs[-1]["http_proxy"] == "http://proxy.example:8118"


def test_miniswe_wrapper_runs_candidate_source_api_not_cli(tmp_path: Path, monkeypatch) -> None:
    _install_fake_harbor(monkeypatch)
    target = tmp_path / "target"
    target.mkdir()
    wrapper = target / "harbor_agent.py"
    wrapper.write_text(Path("templates/target/harbor/miniswe_source_agent.py").read_text())
    module = _load(wrapper)

    class Environment:
        def __init__(self) -> None:
            self.commands = []
            self.envs = []

    environment = Environment()
    agent = module.MiniSweSourceAgent(model_name="openai/test-model")
    asyncio.run(agent.run("Fix the bug.", environment, object()))

    joined = "\n".join(environment.commands)
    assert "mini-swe-agent --" not in joined
    assert "uv run --project /installed-agent/miniswe-source python" in joined
    assert "get_config_from_spec" in joined
    assert "DefaultAgent" in joined
    assert "from minisweagent.environments.local import LocalEnvironment" in joined
    assert "from minisweagent.models.litellm_model import LitellmModel" in joined
    env = environment.envs[-1]
    assert env["MSWEA_MODEL_NAME"] == "openai/test-model"
    assert env["OPENAI_API_KEY"] == "test-key"
    assert env["OPENAI_BASE_URL"] == "https://llm.example/v1"
    assert env["OPENAI_API_BASE"] == "https://llm.example/v1"


def test_miniswe_runtime_unsets_inherited_proxies_but_install_keeps_proxy(tmp_path: Path, monkeypatch) -> None:
    _install_fake_harbor(monkeypatch)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, f"http://inherited-{name.lower()}.example:8118")

    target = tmp_path / "target"
    target.mkdir()
    wrapper = target / "harbor_agent.py"
    wrapper.write_text(Path("templates/target/harbor/miniswe_source_agent.py").read_text())
    module = _load(wrapper)

    class Environment:
        def __init__(self) -> None:
            self.commands = []
            self.envs = []

    environment = Environment()
    agent = module.MiniSweSourceAgent(model_name="openai/test-model")
    asyncio.run(agent.run("Fix the bug.", environment, object()))

    proxy_names = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
    unset_command = f"unset {' '.join(proxy_names)}"
    runtime_command = environment.commands[-1]
    assert unset_command in runtime_command
    assert runtime_command.index(unset_command) < runtime_command.index("uv run --project")
    assert set(proxy_names).isdisjoint(environment.envs[-1])

    install_env = agent._install_env()
    assert install_env["HTTP_PROXY"] == "http://proxy.example:8118"
    assert install_env["HTTPS_PROXY"] == "http://proxy.example:8118"
    assert install_env["http_proxy"] == "http://proxy.example:8118"
    assert install_env["https_proxy"] == "http://proxy.example:8118"


def test_init_with_local_miniswe_seed_writes_target_harbor_wrapper(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module
    from evolve.workspace import InitOptions, init_workspace

    seed = tmp_path / "miniswe"
    (seed / "src" / "minisweagent").mkdir(parents=True)
    (seed / "src" / "minisweagent" / "__init__.py").write_text("__version__ = '0.test'\n")
    (seed / "pyproject.toml").write_text("[project]\nname = 'mini-swe-agent'\nversion = '0.test'\n")
    workspace = tmp_path / "workspace"
    config = workspace_module.default_config("hill_climb", workspace.name)
    config["target"]["harbor_agent"] = "miniswe-source"
    config["evaluator"]["agent"] = "target.harbor_agent:MiniSweSourceAgent"
    monkeypatch.setattr(workspace_module, "default_config", lambda recipe, experiment_id: config)

    init_workspace(InitOptions(workspace=workspace, recipe="hill_climb", seed=str(seed)))

    wrapper = workspace / "target" / "harbor_agent.py"
    assert wrapper.exists()
    assert "class MiniSweSourceAgent(MiniSweAgent):" in wrapper.read_text()


def test_init_with_local_miniswe_seed_excludes_virtualenv_cache(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module
    from evolve.workspace import InitOptions, init_workspace

    seed = tmp_path / "miniswe"
    (seed / "src" / "minisweagent").mkdir(parents=True)
    (seed / "src" / "minisweagent" / "__init__.py").write_text("__version__ = '0.test'\n")
    (seed / ".venv" / "bin").mkdir(parents=True)
    (seed / ".venv" / "bin" / "python").write_text("not source\n")
    (seed / ".pytest_cache").mkdir()
    (seed / ".env").write_text("OPENAI_API_KEY=must-not-copy\n")
    (seed / ".env.local").write_text("HTTPS_PROXY=http://user:pass@proxy.example\n")
    (seed / "src" / "minisweagent" / ".env.test").write_text("TOKEN=must-not-copy\n")
    (seed / "pyproject.toml").write_text("[project]\nname = 'mini-swe-agent'\nversion = '0.test'\n")
    workspace = tmp_path / "workspace"
    config = workspace_module.default_config("hill_climb", workspace.name)
    config["target"]["harbor_agent"] = "miniswe-source"
    config["evaluator"]["agent"] = "target.harbor_agent:MiniSweSourceAgent"
    monkeypatch.setattr(workspace_module, "default_config", lambda recipe, experiment_id: config)

    init_workspace(InitOptions(workspace=workspace, recipe="hill_climb", seed=str(seed)))

    assert (workspace / "target" / "src" / "minisweagent" / "__init__.py").exists()
    assert not (workspace / "target" / ".venv").exists()
    assert not (workspace / "target" / ".pytest_cache").exists()
    assert not (workspace / "target" / ".env").exists()
    assert not (workspace / "target" / ".env.local").exists()
    assert not (workspace / "target" / "src" / "minisweagent" / ".env.test").exists()
