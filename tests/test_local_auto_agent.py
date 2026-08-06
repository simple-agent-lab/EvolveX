import asyncio
import json
from pathlib import Path

import pytest
from harbor.agents.base import BaseAgent
from harbor.environments.base import ExecResult
from harbor.models.agent.context import AgentContext
from harbor.models.trajectories import Agent, Step, Trajectory

from evolve.integrations.harbor import local_auto_agent as adapter


class FakeEnvironment:
    default_user = None

    def __init__(self, available: set[str] | None = None, environment_type: str = "evolve-local") -> None:
        self.available = available or set()
        self.environment_type = environment_type
        self.commands: list[str] = []

    def type(self) -> str:
        return self.environment_type

    async def exec(self, command: str, **_: object) -> ExecResult:
        self.commands.append(command)
        executable = next((name for name in self.available if f"command -v {name} " in command), None)
        return ExecResult(stdout="", stderr="", return_code=0 if executable else 1)


class FakeDelegate(BaseAgent):
    SUPPORTS_ATIF = True

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.setup_called = False
        self.run_instruction: str | None = None

    @staticmethod
    def name() -> str:
        return "fake-delegate"

    def version(self) -> str:
        return "1.2.3"

    async def setup(self, environment: FakeEnvironment) -> None:
        self.setup_called = True

    async def run(self, instruction: str, environment: FakeEnvironment, context: AgentContext) -> None:
        self.run_instruction = instruction

    def populate_context_post_run(self, context: AgentContext) -> None:
        trajectory = Trajectory(
            schema_version="ATIF-v1.7",
            session_id="local-test",
            agent=Agent(name=self.name(), version=self.version(), model_name=self.model_name),
            steps=[Step(step_id=1, source="user", message="edit the candidate")],
        )
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "trajectory.json").write_text(json.dumps(trajectory.to_json_dict()))


def test_discovers_preferred_installed_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        adapter.shutil, "which", lambda executable, path=None: f"/bin/{executable}" if executable == "claude" else None
    )

    selected = adapter.discover_local_agent()

    assert selected is not None
    assert selected.name == "claude-code"


def test_environment_override_controls_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter.shutil, "which", lambda executable, path=None: f"/bin/{executable}")

    selected = adapter.discover_local_agent(environment={"EVOLVE_LOCAL_AGENT": "gemini", "PATH": "/bin"})

    assert selected is not None
    assert selected.name == "gemini-cli"


def test_delegates_local_run_and_validates_atif(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "discover_local_agent", lambda preferred_agents=None: adapter._spec_by_name("codex"))
    monkeypatch.setattr(adapter, "_import_agent_class", lambda import_path: FakeDelegate)
    logs = tmp_path / "agent"
    agent = adapter.LocalAutoAgent(
        logs_dir=logs,
        model_by_agent={"codex": "gpt-test"},
        preferred_agents=["codex", "claude-code"],
    )
    environment = FakeEnvironment({"codex"})
    context = AgentContext()

    async def exercise() -> None:
        await agent.setup(environment)
        await agent.run("improve target", environment, context)

    asyncio.run(exercise())
    agent.populate_context_post_run(context)

    assert isinstance(agent._delegate, FakeDelegate)
    assert agent._delegate.setup_called is True
    assert agent._delegate.run_instruction == "improve target"
    assert agent.to_agent_info().name == "fake-delegate"
    trajectory = Trajectory.model_validate_json((logs / "trajectory.json").read_text())
    assert trajectory.schema_version == "ATIF-v1.7"
    assert trajectory.steps[0].message == "edit the candidate"


def test_codex_reuses_local_login_without_inheriting_driver_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}")
    monkeypatch.setattr(adapter.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "driver-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://evaluator.invalid")
    monkeypatch.setattr(adapter, "discover_local_agent", lambda preferred_agents=None: adapter._spec_by_name("codex"))
    monkeypatch.setattr(adapter, "_import_agent_class", lambda import_path: FakeDelegate)
    agent = adapter.LocalAutoAgent(logs_dir=tmp_path / "logs", model_name="gpt-test")

    asyncio.run(agent.setup(FakeEnvironment({"codex"})))

    assert isinstance(agent._delegate, FakeDelegate)
    assert agent._delegate.extra_env["CODEX_FORCE_AUTH_JSON"] == "1"
    assert agent._delegate.extra_env["OPENAI_API_KEY"] == ""
    assert agent._delegate.extra_env["OPENAI_BASE_URL"] == ""


def test_requires_local_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "discover_local_agent", lambda preferred_agents=None: adapter._spec_by_name("codex"))
    agent = adapter.LocalAutoAgent(logs_dir=tmp_path, model_name="gpt-test")

    with pytest.raises(ValueError, match="LocalEnvironment"):
        asyncio.run(agent.setup(FakeEnvironment({"codex"}, environment_type="docker")))


def test_reports_all_missing_local_agents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "discover_local_agent", lambda preferred_agents=None: None)
    agent = adapter.LocalAutoAgent(logs_dir=tmp_path, model_name="gpt-test")

    with pytest.raises(RuntimeError, match="codex=missing"):
        asyncio.run(agent.setup(FakeEnvironment()))


def test_rejects_missing_atif_trajectory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "discover_local_agent", lambda preferred_agents=None: adapter._spec_by_name("codex"))
    monkeypatch.setattr(adapter, "_import_agent_class", lambda import_path: FakeDelegate)
    agent = adapter.LocalAutoAgent(logs_dir=tmp_path / "logs", model_name="gpt-test")
    asyncio.run(agent.setup(FakeEnvironment({"codex"})))
    assert isinstance(agent._delegate, FakeDelegate)
    agent._delegate.populate_context_post_run = lambda context: None  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="did not produce Harbor ATIF"):
        agent.populate_context_post_run(AgentContext())
