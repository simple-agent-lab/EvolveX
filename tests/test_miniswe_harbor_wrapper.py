import asyncio
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest
from conftest import git, write_locked_miniswe_seed

ROOT = Path(__file__).resolve().parents[1]
ADAPTER_TEMPLATE = ROOT / "templates" / "workspace" / "evolve_harbor_adapter" / "__init__.py"
ADAPTER_TEMPLATES = (
    ROOT / "templates" / "target" / "harbor" / "miniswe_source_agent.py",
    ADAPTER_TEMPLATE,
)


@pytest.fixture(params=ADAPTER_TEMPLATES, ids=("target", "workspace"))
def adapter_path(request):
    return request.param


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
            fail_on = getattr(environment, "fail_on", None)
            should_fail = fail_on and fail_on in command
            if fail_on == "external uv sync":
                should_fail = "uv sync" in command and "--no-install-local" in command
            elif fail_on == "local uv sync":
                should_fail = "uv sync" in command and "--no-install-local" not in command
            if should_fail:
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
    spec = importlib.util.spec_from_file_location("evolve_harbor_adapter", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_fake_miniswe_models(monkeypatch):
    minisweagent = types.ModuleType("minisweagent")
    models = types.ModuleType("minisweagent.models")
    litellm_model = types.ModuleType("minisweagent.models.litellm_model")
    litellm_response_model = types.ModuleType("minisweagent.models.litellm_response_model")

    class FakeLitellmModel:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class FakeLitellmResponseModel(FakeLitellmModel):
        pass

    class FakeLitellmModelConfig:
        model_fields = {"model_name", "model_kwargs", "cost_tracking"}

    litellm_model.LitellmModel = FakeLitellmModel
    litellm_model.LitellmModelConfig = FakeLitellmModelConfig
    litellm_response_model.LitellmResponseModel = FakeLitellmResponseModel
    monkeypatch.setitem(sys.modules, "minisweagent", minisweagent)
    monkeypatch.setitem(sys.modules, "minisweagent.models", models)
    monkeypatch.setitem(sys.modules, "minisweagent.models.litellm_model", litellm_model)
    monkeypatch.setitem(sys.modules, "minisweagent.models.litellm_response_model", litellm_response_model)
    return FakeLitellmModel, FakeLitellmResponseModel


def _load_model_factory(adapter_path: Path, monkeypatch):
    _install_fake_harbor(monkeypatch)
    module = _load(adapter_path)
    model_classes = _install_fake_miniswe_models(monkeypatch)
    namespace = {}
    exec(module.MODEL_SETUP, namespace)
    return module, namespace["build_model"], model_classes


def test_miniswe_wrapper_forwards_reasoning_effort(adapter_path: Path, monkeypatch) -> None:
    _install_fake_harbor(monkeypatch)
    module = _load(adapter_path)
    monkeypatch.setenv("MINISWE_REASONING_EFFORT", "high")

    source_env = module.MiniSweSourceAgent()._source_env()

    assert source_env["MINISWE_REASONING_EFFORT"] == "high"
    monkeypatch.delenv("MINISWE_REASONING_EFFORT")
    assert "MINISWE_REASONING_EFFORT" not in module.MiniSweSourceAgent()._source_env()


def test_miniswe_wrapper_uses_chat_completions_reasoning_for_openai(adapter_path: Path, monkeypatch) -> None:
    _, build_model, (FakeLitellmModel, FakeLitellmResponseModel) = _load_model_factory(adapter_path, monkeypatch)
    monkeypatch.setenv("MSWEA_MODEL_NAME", "openai/gpt-5.4")
    monkeypatch.setenv("MINISWE_REASONING_EFFORT", "high")

    model = build_model(
        {
            "model": {
                "model_kwargs": {
                    "drop_params": True,
                    "reasoning_effort": "legacy",
                    "reasoning": {"effort": "legacy"},
                    "extra_body": {"existing": "value"},
                }
            }
        }
    )

    assert type(model) is FakeLitellmModel
    assert not isinstance(model, FakeLitellmResponseModel)
    assert model.kwargs["model_name"] == "openai/gpt-5.4"
    assert model.kwargs["cost_tracking"] == "ignore_errors"
    assert model.kwargs["model_kwargs"]["drop_params"] is True
    assert model.kwargs["model_kwargs"]["extra_body"] == {
        "existing": "value",
        "reasoning_effort": "high",
    }
    assert "reasoning_effort" not in model.kwargs["model_kwargs"]
    assert "reasoning" not in model.kwargs["model_kwargs"]


@pytest.mark.parametrize(
    ("model_name", "effort"),
    [("openai/gpt-5.4", None), ("anthropic/claude-sonnet-4", "high")],
    ids=("openai-without-effort", "non-openai-with-effort"),
)
def test_miniswe_wrapper_uses_standard_model_without_openai_reasoning(
    adapter_path: Path,
    monkeypatch,
    model_name: str,
    effort: str | None,
) -> None:
    _, build_model, (FakeLitellmModel, FakeLitellmResponseModel) = _load_model_factory(adapter_path, monkeypatch)
    monkeypatch.setenv("MSWEA_MODEL_NAME", model_name)
    if effort is None:
        monkeypatch.delenv("MINISWE_REASONING_EFFORT", raising=False)
    else:
        monkeypatch.setenv("MINISWE_REASONING_EFFORT", effort)

    model = build_model({"model": {"model_kwargs": {"drop_params": True}}})

    assert type(model) is FakeLitellmModel
    assert not isinstance(model, FakeLitellmResponseModel)
    assert model.kwargs["model_kwargs"] == {"drop_params": True}


def test_miniswe_wrapper_rejects_invalid_reasoning_effort(adapter_path: Path, monkeypatch) -> None:
    _, build_model, _ = _load_model_factory(adapter_path, monkeypatch)
    monkeypatch.setenv("MSWEA_MODEL_NAME", "openai/gpt-5.4")
    monkeypatch.setenv("MINISWE_REASONING_EFFORT", "maximum")

    with pytest.raises(ValueError, match=r"none, low, medium, high, xhigh"):
        build_model({"model": {}})


def test_miniswe_wrapper_reuses_model_setup_for_runner_and_preflight(adapter_path: Path, monkeypatch) -> None:
    _install_fake_harbor(monkeypatch)
    module = _load(adapter_path)

    assert module.RUNNER.startswith(module.MODEL_SETUP)
    assert module.MODEL_PREFLIGHT.startswith(module.MODEL_SETUP)
    assert "model = build_model(config)" in module.RUNNER
    assert "build_model(config)" in module.MODEL_PREFLIGHT


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
    wrapper.write_text(ADAPTER_TEMPLATE.read_text())
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
    monkeypatch.setenv("EVOLVE_CANDIDATE_SOURCE", str(target))
    for name in ("UV_CACHE_DIR", "UV_LINK_MODE", "UV_OFFLINE", "UV_PYTHON", "UV_PYTHON_INSTALL_DIR"):
        monkeypatch.delenv(name, raising=False)
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
    sync_indices = [index for index, command in enumerate(environment.commands) if "uv sync" in command]
    assert len(sync_indices) == 2
    assert "--no-install-local" in environment.commands[sync_indices[0]]
    assert "--no-install-local" not in environment.commands[sync_indices[1]]
    assert 'export PATH="$HOME/.local/bin:$PATH"' in environment.commands[sync_indices[0]]
    for sync_index in sync_indices:
        assert f"unset {' '.join(module.PROXY_NAMES)}" in environment.commands[sync_index]
        sync_env = environment.envs[sync_index]
        assert sync_env == {
            "UV_CACHE_DIR": "/opt/evolve/uv/cache",
            "UV_LINK_MODE": "copy",
            "UV_OFFLINE": "1",
            "UV_PYTHON_INSTALL_DIR": "/opt/evolve/uv/python",
        }
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
    proxy_names = {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    }
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
    wrapper.write_text(ADAPTER_TEMPLATE.read_text())
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
    assert 'env_kwargs["cwd"] = os.environ.get("MINISWE_CWD") or os.getcwd()' in module.RUNNER


def test_miniswe_runtime_and_offline_install_do_not_forward_proxies(tmp_path: Path, monkeypatch) -> None:
    _install_fake_harbor(monkeypatch)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, f"http://inherited-{name.lower()}.example:8118")

    target = tmp_path / "target"
    target.mkdir()
    wrapper = target / "harbor_agent.py"
    wrapper.write_text(ADAPTER_TEMPLATE.read_text())
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
    assert set(proxy_names).isdisjoint(install_env)
    assert install_env["UV_OFFLINE"] == "1"


@pytest.mark.parametrize(
    ("fragment", "code", "failure"),
    [
        ("local uv sync", "local_project_sync_failed", RuntimeError("failed building candidate")),
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
    wrapper.write_text(ADAPTER_TEMPLATE.read_text())
    module = _load(wrapper)
    monkeypatch.setenv("EVOLVE_CANDIDATE_SOURCE", str(target))

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


def test_miniswe_external_dependency_sync_is_infrastructure_owned(tmp_path: Path, monkeypatch) -> None:
    _install_fake_harbor(monkeypatch)
    target = write_locked_miniswe_seed(tmp_path / "target")
    wrapper = target / "harbor_agent.py"
    wrapper.write_text(ADAPTER_TEMPLATE.read_text())
    module = _load(wrapper)
    monkeypatch.setenv("EVOLVE_CANDIDATE_SOURCE", str(target))

    class Environment:
        def __init__(self) -> None:
            self.commands = []
            self.envs = []
            self.uploads = []
            self.fail_on = "external uv sync"
            self.failure = RuntimeError("offline cache miss")

        async def upload_dir(self, source_dir, target_dir):
            self.uploads.append((Path(source_dir), target_dir))

        async def upload_file(self, source_path, target_path):
            self.uploads.append((Path(source_path), target_path))

    with pytest.raises(module.EvolveRuntimeInfrastructureError) as raised:
        asyncio.run(module.MiniSweSourceAgent().install(Environment()))

    assert str(raised.value) == ("EVOLVE_RUNTIME_INFRASTRUCTURE: external_dependency_sync_failed: offline cache miss")


def test_miniswe_offline_runtime_never_downloads_uv(tmp_path: Path, monkeypatch) -> None:
    _install_fake_harbor(monkeypatch)
    target = write_locked_miniswe_seed(tmp_path / "target")
    wrapper = target / "harbor_agent.py"
    wrapper.write_text(ADAPTER_TEMPLATE.read_text())
    module = _load(wrapper)
    monkeypatch.setenv("EVOLVE_CANDIDATE_SOURCE", str(target))
    monkeypatch.setenv("UV_OFFLINE", "1")
    monkeypatch.delenv("EVOLVE_UV_BINARY", raising=False)
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)

    class Environment:
        def __init__(self) -> None:
            self.commands = []
            self.envs = []
            self.uploads = []
            self.fail_on = "EVOLVE_UV_BOOTSTRAP_MISSING"

        async def upload_dir(self, source_dir, target_dir):
            self.uploads.append((Path(source_dir), target_dir))

        async def upload_file(self, source_path, target_path):
            self.uploads.append((Path(source_path), target_path))

    environment = Environment()
    with pytest.raises(
        module.EvolveRuntimeInfrastructureError,
        match="EVOLVE_RUNTIME_INFRASTRUCTURE: uv_bootstrap_failed",
    ):
        asyncio.run(module.MiniSweSourceAgent().install(environment))

    bootstrap = next(command for command in environment.commands if "EVOLVE_UV_BOOTSTRAP_MISSING" in command)
    assert "curl" not in bootstrap
    assert f"unset {' '.join(module.PROXY_NAMES)}" in bootstrap


def test_miniswe_install_rejects_missing_lock_before_upload(tmp_path: Path, monkeypatch) -> None:
    _install_fake_harbor(monkeypatch)
    target = write_locked_miniswe_seed(tmp_path / "target")
    (target / "uv.lock").unlink()
    wrapper = target / "harbor_agent.py"
    wrapper.write_text(ADAPTER_TEMPLATE.read_text())
    module = _load(wrapper)
    monkeypatch.setenv("EVOLVE_CANDIDATE_SOURCE", str(target))

    class Environment:
        uploads = []

    with pytest.raises(RuntimeError, match="EVOLVE_CANDIDATE_INVALID: lock_missing"):
        asyncio.run(module.MiniSweSourceAgent().install(Environment()))

    assert Environment.uploads == []


def test_init_with_local_miniswe_seed_writes_protected_harbor_adapter(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module
    from evolve.workspace import InitOptions, init_workspace

    seed = write_locked_miniswe_seed(tmp_path / "miniswe")
    (seed / ".gitignore").write_text("uv.lock\n")
    expected_lock = (seed / "uv.lock").read_bytes()
    workspace = tmp_path / "workspace"
    config = workspace_module.default_config("hill_climb", workspace.name)
    config["target"]["harbor_agent"] = "miniswe-source"
    config["evaluator"]["agent"] = "evolve_harbor_adapter:MiniSweSourceAgent"
    monkeypatch.setattr(workspace_module, "default_config", lambda recipe, experiment_id: config)

    init_workspace(InitOptions(workspace=workspace, recipe="hill_climb", seed=str(seed)))

    wrapper = workspace / "evolve_harbor_adapter" / "__init__.py"
    assert wrapper.exists()
    assert "class MiniSweSourceAgent(MiniSweAgent):" in wrapper.read_text()
    assert not (workspace / "target" / "harbor_agent.py").exists()
    assert (workspace / "target" / "uv.lock").read_bytes() == expected_lock
    assert git(workspace, "ls-files", "target/uv.lock") == "target/uv.lock"


def test_init_tracks_seed_lockfile_even_when_seed_gitignore_excludes_it(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module
    from evolve.workspace import InitOptions, init_workspace

    seed = write_locked_miniswe_seed(tmp_path / "miniswe")
    (seed / ".gitignore").write_text("uv.lock\n")
    workspace = tmp_path / "workspace"
    config = workspace_module.default_config("hill_climb", workspace.name)
    config["target"]["harbor_agent"] = "miniswe-source"
    config["evaluator"]["agent"] = "evolve_harbor_adapter:MiniSweSourceAgent"
    monkeypatch.setattr(workspace_module, "default_config", lambda recipe, experiment_id: config)

    init_workspace(InitOptions(workspace=workspace, recipe="hill_climb", seed=str(seed)))

    git(workspace, "cat-file", "-e", "gen/0:target/uv.lock")


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

    assert (workspace / "evolve_harbor_adapter" / "__init__.py").is_file()
    assert not (workspace / "target" / "harbor_agent.py").exists()


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
    config["evaluator"]["agent"] = "evolve_harbor_adapter:MiniSweSourceAgent"
    monkeypatch.setattr(workspace_module, "default_config", lambda recipe, experiment_id: config)

    init_workspace(InitOptions(workspace=workspace, recipe="hill_climb", seed=str(seed)))

    assert (workspace / "target" / "src" / "minisweagent" / "__init__.py").exists()
    assert not (workspace / "target" / ".venv").exists()
    assert not (workspace / "target" / ".pytest_cache").exists()
    assert not (workspace / "target" / ".env").exists()
    assert not (workspace / "target" / ".env.local").exists()
    assert not (workspace / "target" / "src" / "minisweagent" / ".env.test").exists()
