"""Auto-discover an installed local CLI agent and delegate to Harbor.

The adapter is intentionally limited to ``evolve.harbor_local:LocalEnvironment``.
It preserves Harbor's installed-agent implementations as the authority for CLI
invocation, authentication, usage accounting, and ATIF conversion while adding a
single backend-agnostic entry point for local Evolve runs.
"""

from __future__ import annotations

import os
import shlex
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, override

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trajectories import Trajectory
from harbor.models.trial.result import AgentInfo

LOCAL_ENVIRONMENT_TYPE = "evolve-local"


@dataclass(frozen=True)
class LocalAgentSpec:
    name: str
    executable: str
    import_path: str
    aliases: tuple[str, ...] = ()
    requires_model: bool = False


LOCAL_AGENT_SPECS = (
    LocalAgentSpec(
        name="codex",
        executable="codex",
        import_path="harbor.agents.installed.codex:Codex",
        aliases=("openai-codex",),
        requires_model=True,
    ),
    LocalAgentSpec(
        name="claude-code",
        executable="claude",
        import_path="harbor.agents.installed.claude_code:ClaudeCode",
        aliases=("claude",),
    ),
    LocalAgentSpec(
        name="gemini-cli",
        executable="gemini",
        import_path="harbor.agents.installed.gemini_cli:GeminiCli",
        aliases=("gemini",),
        requires_model=True,
    ),
    LocalAgentSpec(
        name="opencode",
        executable="opencode",
        import_path="harbor.agents.installed.opencode:OpenCode",
        aliases=("open-code",),
        requires_model=True,
    ),
)


def _normalized_preferences(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return tuple(spec.name for spec in LOCAL_AGENT_SPECS)
    values = [value] if isinstance(value, str) else list(value)
    normalized: list[str] = []
    for entry in values:
        for token in str(entry).split(","):
            name = token.strip().lower()
            if name and name not in normalized:
                normalized.append(name)
    if not normalized:
        raise ValueError("preferred_agents must contain at least one agent name")
    return tuple(normalized)


def _spec_by_name(name: str) -> LocalAgentSpec:
    normalized = name.strip().lower()
    for spec in LOCAL_AGENT_SPECS:
        if normalized == spec.name or normalized in spec.aliases:
            return spec
    available = ", ".join(spec.name for spec in LOCAL_AGENT_SPECS)
    raise ValueError(f"unknown local agent {name!r}; available: {available}")


def discover_local_agent(
    preferred_agents: str | Sequence[str] | None = None,
    *,
    environment: dict[str, str] | None = None,
) -> LocalAgentSpec | None:
    """Return the first preferred CLI available in the host process PATH."""
    source = os.environ if environment is None else environment
    configured = source.get("EVOLVE_LOCAL_AGENT")
    preferences = _normalized_preferences(configured or preferred_agents)
    search_path = source.get("PATH")
    for name in preferences:
        spec = _spec_by_name(name)
        if shutil.which(spec.executable, path=search_path):
            return spec
    return None


def _import_agent_class(import_path: str) -> type[BaseAgent]:
    module_name, separator, class_name = import_path.partition(":")
    if not separator:
        raise ValueError(f"invalid Harbor agent import path: {import_path}")
    module = __import__(module_name, fromlist=[class_name])
    value = getattr(module, class_name)
    if not isinstance(value, type) or not issubclass(value, BaseAgent):
        raise TypeError(f"Harbor agent import is not a BaseAgent subclass: {import_path}")
    return value


class LocalAutoAgent(BaseAgent):
    """Use the first supported CLI already installed on the local machine."""

    SUPPORTS_ATIF = True

    def __init__(
        self,
        *args: Any,
        preferred_agents: str | Sequence[str] | None = None,
        model_by_agent: dict[str, str] | None = None,
        agent_kwargs_by_agent: dict[str, dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._preferences = _normalized_preferences(preferred_agents)
        self._model_by_agent = dict(model_by_agent or {})
        self._agent_kwargs_by_agent = dict(agent_kwargs_by_agent or {})
        self._delegate: BaseAgent | None = None
        self._selected_spec = discover_local_agent(self._preferences)

    @staticmethod
    @override
    def name() -> str:
        return "evolve-local-auto"

    @override
    def version(self) -> str | None:
        return self._delegate.version() if self._delegate is not None else None

    @override
    def to_agent_info(self) -> AgentInfo:
        if self._delegate is not None:
            return self._delegate.to_agent_info()
        return super().to_agent_info()

    def _model_for(self, spec: LocalAgentSpec) -> str | None:
        configured = self._model_by_agent.get(spec.name)
        return configured or self.model_name

    def _extra_env_for(self, spec: LocalAgentSpec) -> dict[str, str]:
        values = self.extra_env
        if spec.name != "codex":
            return values

        explicit_auth = values.get("CODEX_AUTH_JSON_PATH") or os.environ.get("CODEX_AUTH_JSON_PATH")
        force_auth = values.get("CODEX_FORCE_AUTH_JSON") or os.environ.get("CODEX_FORCE_AUTH_JSON")
        default_auth = Path.home() / ".codex" / "auth.json"
        if not explicit_auth and not force_auth and default_auth.is_file():
            values["CODEX_FORCE_AUTH_JSON"] = "1"
            # A local subscription login should not silently inherit evaluator
            # endpoints or API keys exported in the parent process.
            values.setdefault("OPENAI_API_KEY", "")
            values.setdefault("OPENAI_BASE_URL", "")
            values.setdefault("OPENAI_API_BASE", "")
        return values

    def _create_delegate(self, spec: LocalAgentSpec) -> BaseAgent:
        model_name = self._model_for(spec)
        if spec.requires_model and not model_name:
            raise ValueError(
                f"local agent {spec.name!r} requires a model; set operators.mutate.model or agent_kwargs.model_by_agent"
            )
        agent_class = _import_agent_class(spec.import_path)
        delegate_kwargs = dict(self._agent_kwargs_by_agent.get(spec.name) or {})
        delegate = agent_class(
            logs_dir=self.logs_dir,
            model_name=model_name,
            logger=self.logger,
            mcp_servers=self.mcp_servers,
            skills_dir=self.skills_dir,
            extra_env=self._extra_env_for(spec),
            **delegate_kwargs,
        )
        delegate.session_id = self.session_id
        delegate.context_id = self.context_id
        return delegate

    async def _detect_in_environment(self, environment: BaseEnvironment) -> LocalAgentSpec:
        configured = self.extra_env.get("EVOLVE_LOCAL_AGENT") or os.environ.get("EVOLVE_LOCAL_AGENT")
        preferences = _normalized_preferences(configured or self._preferences)
        diagnostics: list[str] = []
        for name in preferences:
            spec = _spec_by_name(name)
            result = await environment.exec(
                command=f"command -v {shlex.quote(spec.executable)} >/dev/null 2>&1",
                timeout_sec=10,
            )
            diagnostics.append(f"{spec.name}={'found' if result.return_code == 0 else 'missing'}")
            if result.return_code == 0:
                return spec
        raise RuntimeError(
            "no supported local agent CLI found; install one or set EVOLVE_LOCAL_AGENT. " + ", ".join(diagnostics)
        )

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        if environment.type() != LOCAL_ENVIRONMENT_TYPE:
            raise ValueError(
                f"LocalAutoAgent only supports evolve.harbor_local:LocalEnvironment; received {environment.type()!r}"
            )
        spec = self._selected_spec or await self._detect_in_environment(environment)
        self._selected_spec = spec
        self._delegate = self._create_delegate(spec)
        await self._delegate.setup(environment)

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        if self._delegate is None:
            raise RuntimeError("LocalAutoAgent.setup() must run before run()")
        await self._delegate.run(instruction, environment, context)

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        if self._delegate is None:
            raise RuntimeError("LocalAutoAgent has no selected delegate")
        self._delegate.populate_context_post_run(context)
        trajectory_path = self.logs_dir / "trajectory.json"
        if not trajectory_path.is_file():
            raise RuntimeError(
                f"local agent {self._selected_spec.name if self._selected_spec else 'unknown'} "
                "did not produce Harbor ATIF trajectory.json"
            )
        Trajectory.model_validate_json(trajectory_path.read_text())
