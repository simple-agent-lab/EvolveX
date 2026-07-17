import asyncio
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest
from conftest import write_locked_miniswe_seed


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
            if getattr(environment, "fail_on", None) and environment.fail_on in command:
                raise getattr(environment, "failure", RuntimeError("simulated command failure"))

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
    (target / "uv.lock").write_text("version = 1\nrevision = 1\nrequires-python = '>=3.11'\n")
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
    assert "apt-get" not in joined
    assert "apk add" not in joined
    assert 'cp /tmp/evolve-uv "$HOME/.local/bin/uv"' in joined
    assert '"$HOME/.local/bin/uv" --version' in joined
    assert 'rm -f "$HOME/.local/bin/uv"' in joined
    assert "uv tool install" not in joined
    assert "mini-swe-agent --" not in joined
    assert "curl -LsSf https://astral.sh/uv/0.7.13/install.sh" in joined
    assert "uv sync --project /installed-agent/miniswe-source --frozen" in joined
    assert "/installed-agent/miniswe-source/.venv/bin/python" in joined
    assert "uv run --project /installed-agent/miniswe-source" not in joined
    assert "from minisweagent.agents.default import DefaultAgent" in joined
    assert sum("uv sync" in command for command in environment.commands) == 1
    sync_index = next(index for index, command in enumerate(environment.commands) if "uv sync" in command)
    assert 'export PATH="$HOME/.local/bin:$PATH"' in environment.commands[sync_index]
    assert environment.envs[sync_index]["http_proxy"] == "http://proxy.example:8118"
    assert environment.envs[sync_index]["UV_CACHE_DIR"] == "/installed-agent/uv-cache"
    model_index = next(
        index for index, command in enumerate(environment.commands) if "EVOLVE_PREFLIGHT_MODEL" in command
    )
    evidence_index = next(
        index for index, command in enumerate(environment.commands) if "evolve-runtime.json" in command
    )
    assert model_index < evidence_index
    assert '"frozen_sync": true' in environment.commands[evidence_index]
    assert '"miniswe_import": true' in environment.commands[evidence_index]
    assert '"model_path_init": true' in environment.commands[evidence_index]
    proxy_names = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"}
    assert proxy_names.isdisjoint(environment.envs[model_index])
    assert environment.envs[model_index]["OPENAI_API_KEY"] == "test-key"
    assert environment.envs[model_index]["OPENAI_BASE_URL"] == "https://llm.example/v1"
    assert f"unset {' '.join(module.PROXY_NAMES)}" in environment.commands[model_index]


def test_miniswe_wrapper_runs_candidate_source_api_not_cli(tmp_path: Path, monkeypatch) -> None:
    _install_fake_harbor(monkeypatch)
    monkeypatch.setenv("MINISWE_STEP_LIMIT", "100")
    monkeypatch.setenv("MINISWE_COST_LIMIT", "3.0")
    monkeypatch.setenv("MINISWE_ENV_TIMEOUT", "30")
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
    assert "/installed-agent/miniswe-source/.venv/bin/python /tmp/miniswe-source-run.py" in joined
    assert "uv run --project /installed-agent/miniswe-source" not in joined
    assert "get_config_from_spec" in joined
    assert "DefaultAgent" in joined
    assert "from minisweagent.environments.local import LocalEnvironment" in joined
    assert "from minisweagent.models.litellm_model import LitellmModel" in joined
    env = environment.envs[-1]
    assert env["MSWEA_MODEL_NAME"] == "openai/test-model"
    assert env["OPENAI_API_KEY"] == "test-key"
    assert env["OPENAI_BASE_URL"] == "https://llm.example/v1"
    assert env["OPENAI_API_BASE"] == "https://llm.example/v1"
    assert env["MINISWE_STEP_LIMIT"] == "100"
    assert env["MINISWE_COST_LIMIT"] == "3.0"
    assert env["MINISWE_ENV_TIMEOUT"] == "30"
    assert 'agent_kwargs["step_limit"] = int(os.environ.get("MINISWE_STEP_LIMIT"' in module.RUNNER
    assert 'agent_kwargs["cost_limit"] = float(os.environ.get("MINISWE_COST_LIMIT"' in module.RUNNER
    assert 'env_kwargs["timeout"] = int(os.environ.get("MINISWE_ENV_TIMEOUT"' in module.RUNNER


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
    assert runtime_command.index(unset_command) < runtime_command.index(".venv/bin/python")
    assert set(proxy_names).isdisjoint(environment.envs[-1])

    install_env = agent._install_env()
    assert install_env["HTTP_PROXY"] == "http://proxy.example:8118"
    assert install_env["HTTPS_PROXY"] == "http://proxy.example:8118"
    assert install_env["http_proxy"] == "http://proxy.example:8118"
    assert install_env["https_proxy"] == "http://proxy.example:8118"


@pytest.mark.parametrize(
    ("fragment", "code", "failure"),
    [
        ("uv sync", "frozen_sync_failed", RuntimeError("failed building litellm==1.92.0")),
        ("EVOLVE_PREFLIGHT_MINISWE", "miniswe_import_failed", ImportError("minisweagent")),
        ("EVOLVE_PREFLIGHT_MODEL", "model_path_import_failed", ModuleNotFoundError("fastapi")),
    ],
    ids=["litellm-build-failure", "miniswe-import-failure", "missing-fastapi"],
)
def test_miniswe_install_classifies_candidate_phase_failures(
    tmp_path: Path,
    monkeypatch,
    fragment: str,
    code: str,
    failure: Exception,
) -> None:
    _install_fake_harbor(monkeypatch)
    target = write_locked_miniswe_seed(tmp_path / "target")
    wrapper = target / "harbor_agent.py"
    wrapper.write_text(Path("templates/target/harbor/miniswe_source_agent.py").read_text())
    module = _load(wrapper)

    class Environment:
        def __init__(self) -> None:
            self.commands = []
            self.envs = []
            self.uploads = []
            self.fail_on = fragment
            self.failure = failure

        async def upload_dir(self, source_dir, target_dir):
            self.uploads.append((Path(source_dir), target_dir))

        async def upload_file(self, source_path, target_path):
            self.uploads.append((Path(source_path), target_path))

    with pytest.raises(RuntimeError, match=f"EVOLVE_CANDIDATE_INVALID: {code}"):
        asyncio.run(module.MiniSweSourceAgent().install(Environment()))


def test_miniswe_install_rejects_missing_lock_before_upload(tmp_path: Path, monkeypatch) -> None:
    _install_fake_harbor(monkeypatch)
    target = write_locked_miniswe_seed(tmp_path / "target")
    (target / "uv.lock").unlink()
    wrapper = target / "harbor_agent.py"
    wrapper.write_text(Path("templates/target/harbor/miniswe_source_agent.py").read_text())
    module = _load(wrapper)

    class Environment:
        uploads = []

    with pytest.raises(RuntimeError, match="EVOLVE_CANDIDATE_INVALID: lock_missing"):
        asyncio.run(module.MiniSweSourceAgent().install(Environment()))

    assert Environment.uploads == []


def test_init_with_local_miniswe_seed_writes_target_harbor_wrapper(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module
    from evolve.workspace import InitOptions, init_workspace

    seed = write_locked_miniswe_seed(tmp_path / "miniswe")
    expected_lock = (seed / "uv.lock").read_bytes()
    workspace = tmp_path / "workspace"
    config = workspace_module.default_config("hill_climb", workspace.name)
    config["target"]["harbor_agent"] = "miniswe-source"
    config["evaluator"]["agent"] = "target.harbor_agent:MiniSweSourceAgent"
    monkeypatch.setattr(workspace_module, "default_config", lambda recipe, experiment_id: config)

    init_workspace(InitOptions(workspace=workspace, recipe="hill_climb", seed=str(seed)))

    wrapper = workspace / "target" / "harbor_agent.py"
    assert wrapper.exists()
    assert "class MiniSweSourceAgent(MiniSweAgent):" in wrapper.read_text()
    assert (workspace / "target" / "uv.lock").read_bytes() == expected_lock


def test_init_does_not_enforce_package_manager_files(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module
    from evolve.workspace import InitOptions, init_workspace

    seed = write_locked_miniswe_seed(tmp_path / "miniswe")
    (seed / "uv.lock").unlink()
    workspace = tmp_path / "workspace"
    config = workspace_module.default_config("hill_climb", workspace.name)
    config["target"]["harbor_agent"] = "miniswe-source"
    monkeypatch.setattr(workspace_module, "default_config", lambda recipe, experiment_id: config)

    init_workspace(InitOptions(workspace=workspace, recipe="hill_climb", seed=str(seed)))

    assert (workspace / "target" / "harbor_agent.py").is_file()


def test_init_with_local_miniswe_seed_excludes_virtualenv_cache(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module
    from evolve.workspace import InitOptions, init_workspace

    seed = write_locked_miniswe_seed(tmp_path / "miniswe")
    (seed / ".venv" / "bin").mkdir(parents=True)
    (seed / ".venv" / "bin" / "python").write_text("not source\n")
    (seed / ".pytest_cache").mkdir()
    (seed / ".env").write_text("OPENAI_API_KEY=must-not-copy\n")
    (seed / ".env.local").write_text("HTTPS_PROXY=http://user:pass@proxy.example\n")
    (seed / "src" / "minisweagent" / ".env.test").write_text("TOKEN=must-not-copy\n")
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
