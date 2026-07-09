import asyncio
import importlib.util
import sys
import types
from pathlib import Path


def _install_fake_harbor(monkeypatch):
    root = types.ModuleType("harbor")
    agents = types.ModuleType("harbor.agents")
    installed = types.ModuleType("harbor.agents.installed")
    mini = types.ModuleType("harbor.agents.installed.mini_swe_agent")

    class MiniSweAgent:
        async def exec_as_agent(self, environment, command: str):
            environment.commands.append(command)

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
    (target / "mini_swe_agent").mkdir()
    wrapper = target / "harbor_agent.py"
    wrapper.write_text(Path("templates/target/harbor/miniswe_source_agent.py").read_text())
    module = _load(wrapper)

    class Environment:
        def __init__(self) -> None:
            self.uploads = []
            self.commands = []

        async def upload_dir(self, source_dir, target_dir):
            self.uploads.append((Path(source_dir), target_dir))

    environment = Environment()
    agent = module.MiniSweSourceAgent()
    asyncio.run(agent.install(environment))

    assert issubclass(module.MiniSweSourceAgent, base)
    assert environment.uploads == [(target.resolve(), "/installed-agent/miniswe-source")]
    assert "uv tool install --force /installed-agent/miniswe-source" in environment.commands
    assert any("mini-swe-agent" in command for command in environment.commands)
    assert any("uv run --project /installed-agent/miniswe-source" in command for command in environment.commands)
    assert any("mini_swe_agent.__file__" in command for command in environment.commands)


def test_init_with_local_miniswe_seed_writes_target_harbor_wrapper(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module
    from evolve.workspace import InitOptions, init_workspace

    seed = tmp_path / "miniswe"
    (seed / "mini_swe_agent").mkdir(parents=True)
    (seed / "mini_swe_agent" / "__init__.py").write_text("__version__ = '0.test'\n")
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
