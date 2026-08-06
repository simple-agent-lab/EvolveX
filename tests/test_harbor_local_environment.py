from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class _ExecResult:
    stdout: str | None = None
    stderr: str | None = None
    return_code: int = 0


class _BaseEnvironment:
    def __init__(
        self,
        *,
        environment_dir,
        session_id,
        task_env_config,
        trial_paths=None,
        mounts=None,
        logger=None,
        **_kwargs,
    ):
        self.environment_dir = Path(environment_dir)
        self.session_id = session_id
        self.task_env_config = task_env_config
        self.trial_paths = trial_paths
        self._mounts = mounts or []
        self.logger = logger or logging.getLogger("local-environment-test")
        self.default_user = None
        self._validate_definition()

    @property
    def os(self):
        return self.task_env_config.os

    def _resolve_user(self, user):
        return user if user is not None else self.default_user

    def _merge_env(self, env):
        return env

    def _output_callback(self):
        return None

    async def _upload_environment_dir_after_start(self):
        if (
            self.task_env_config.docker_image
            and not (self.environment_dir / "Dockerfile").exists()
            and not (self.environment_dir / "docker-compose.yaml").exists()
            and any(self.environment_dir.iterdir())
        ):
            await self.upload_dir(self.environment_dir, self.task_env_config.workdir or "/app")


class _Capabilities:
    def __init__(self, **values):
        self.__dict__.update(values)


class _TaskOS:
    LINUX = "linux"
    WINDOWS = "windows"


class _EnvironmentPaths:
    @classmethod
    def for_os(cls, _os):
        return types.SimpleNamespace(
            logs_dir="/logs",
            agent_dir="/logs/agent",
            verifier_dir="/logs/verifier",
            artifacts_dir="/logs/artifacts",
            tests_dir="/tests",
            solution_dir="/solution",
            default_skills_dir="/harbor/skills",
        )


@dataclass
class _TaskConfig:
    os: str = _TaskOS.LINUX
    workdir: str | None = None
    docker_image: str | None = None


def _load_module(monkeypatch: pytest.MonkeyPatch):
    modules = {
        "harbor": types.ModuleType("harbor"),
        "harbor.environments": types.ModuleType("harbor.environments"),
        "harbor.environments.base": types.ModuleType("harbor.environments.base"),
        "harbor.environments.capabilities": types.ModuleType("harbor.environments.capabilities"),
        "harbor.models": types.ModuleType("harbor.models"),
        "harbor.models.task": types.ModuleType("harbor.models.task"),
        "harbor.models.task.config": types.ModuleType("harbor.models.task.config"),
        "harbor.models.trial": types.ModuleType("harbor.models.trial"),
        "harbor.models.trial.paths": types.ModuleType("harbor.models.trial.paths"),
    }
    modules["harbor.environments.base"].BaseEnvironment = _BaseEnvironment
    modules["harbor.environments.base"].ExecResult = _ExecResult
    modules["harbor.environments.capabilities"].EnvironmentCapabilities = _Capabilities
    modules["harbor.environments.capabilities"].EnvironmentResourceCapabilities = _Capabilities
    modules["harbor.models.task.config"].TaskOS = _TaskOS
    modules["harbor.models.trial.paths"].EnvironmentPaths = _EnvironmentPaths
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    path = Path(__file__).parents[1] / "src" / "evolve" / "harbor_local.py"
    spec = importlib.util.spec_from_file_location("harbor_local_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _environment(module, tmp_path: Path, **kwargs):
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir(exist_ok=True)
    return module.LocalEnvironment(
        environment_dir=environment_dir,
        session_id="trial-1",
        task_env_config=_TaskConfig(workdir="/workspace"),
        trial_paths=types.SimpleNamespace(trial_dir=tmp_path / "trial"),
        **kwargs,
    )


def test_local_environment_executes_in_current_namespace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module(monkeypatch)
    environment = _environment(module, tmp_path)
    asyncio.run(environment.start(force_build=False))

    result = asyncio.run(
        environment.exec(
            'test "$HARBOR_WORKDIR" = "$(pwd)" '
            '&& printf \'%s\' "$LOCAL_VALUE" > "$HARBOR_WORKDIR/output.txt" '
            '&& cat "$HARBOR_WORKDIR/output.txt"',
            env={"LOCAL_VALUE": "ok"},
        )
    )

    assert result.return_code == 0
    assert result.stdout == "ok"
    assert result.stderr == ""
    assert (tmp_path / "trial" / "local-environment" / "workspace" / "output.txt").read_text() == "ok"
    assert (tmp_path / "trial" / "local-environment" / "logs" / "agent").is_dir()


def test_local_environment_rewrites_nested_harbor_path_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module(monkeypatch)
    environment = _environment(module, tmp_path)

    rewritten = environment._rewrite_command("touch /logs/agent/output.txt")

    expected = tmp_path / "trial" / "local-environment" / "logs" / "agent" / "output.txt"
    assert rewritten == f"touch {expected}"


def test_local_environment_copies_directory_contents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module(monkeypatch)
    environment = _environment(module, tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("payload")
    target = "/tests/target"
    downloaded = tmp_path / "downloaded"

    asyncio.run(environment.upload_dir(source, str(target)))
    asyncio.run(environment.download_dir(target, downloaded))

    mapped_target = tmp_path / "trial" / "local-environment" / "tests" / "target"
    assert (mapped_target / "file.txt").read_text() == "payload"
    assert (downloaded / "file.txt").read_text() == "payload"


def test_local_environment_stages_compiled_inputs_for_prebuilt_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module(monkeypatch)
    environment_dir = tmp_path / "environment"
    workspace = environment_dir / "task" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "candidate.txt").write_text("candidate\n")
    environment = module.LocalEnvironment(
        environment_dir=environment_dir,
        session_id="trial",
        task_env_config=_TaskConfig(workdir="/app", docker_image="ubuntu:latest"),
        trial_paths=types.SimpleNamespace(trial_dir=tmp_path / "trial"),
    )

    asyncio.run(environment.start(force_build=False))

    staged = tmp_path / "trial" / "local-environment" / "app" / "task" / "workspace" / "candidate.txt"
    assert staged.read_text() == "candidate\n"


def test_local_environment_stages_inputs_when_task_has_dockerfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module(monkeypatch)
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir()
    (environment_dir / "Dockerfile").write_text("FROM scratch\n")
    (environment_dir / "paper.pdf").write_bytes(b"paper")
    environment = module.LocalEnvironment(
        environment_dir=environment_dir,
        session_id="trial",
        task_env_config=_TaskConfig(workdir="/app"),
        trial_paths=types.SimpleNamespace(trial_dir=tmp_path / "trial"),
    )

    asyncio.run(environment.start(force_build=False))

    staged = tmp_path / "trial" / "local-environment" / "app"
    assert (staged / "paper.pdf").read_bytes() == b"paper"
    assert (staged / "Dockerfile").read_text() == "FROM scratch\n"


def test_local_environment_rewrites_virtual_paths_inside_verifier_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module(monkeypatch)
    environment = _environment(module, tmp_path)
    source = tmp_path / "tests-source"
    source.mkdir()
    script = source / "test.sh"
    script.write_text("#!/bin/sh\nmkdir -p /logs/verifier\nprintf '1\\n' > /logs/verifier/reward.txt\n")

    asyncio.run(environment.start(force_build=False))
    asyncio.run(environment.upload_dir(source, "/tests"))
    result = asyncio.run(environment.exec("chmod +x /tests/test.sh && /tests/test.sh"))

    reward = tmp_path / "trial" / "local-environment" / "logs" / "verifier" / "reward.txt"
    assert result.return_code == 0
    assert reward.read_text() == "1\n"


def test_local_environment_ignores_container_definition(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module(monkeypatch)
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir()
    (environment_dir / "docker-compose.yaml").write_text("services: {}\n")

    environment = module.LocalEnvironment(
        environment_dir=environment_dir,
        session_id="trial",
        task_env_config=_TaskConfig(workdir="/workspace"),
        trial_paths=types.SimpleNamespace(trial_dir=tmp_path / "trial"),
    )

    assert environment.type() == "evolve-local"
