"""Prime Agent Harbor adapter, including its continual-harness state.

Prime Agent descends from ``badlogic/pi-mono`` and kept that CLI contract, so
the invocation and usage accounting mirror Harbor's ``pi`` adapter. What is
specific to Prime is the continual harness: supplemental prompts, memories,
skills and subagent specs that Prime refines itself during a run. This adapter
can pin a run to a given harness checkpoint and export whatever the run left
behind, which is what makes a chain of harness generations observable.

Two upstream behaviours are easy to trip over and are handled here explicitly:

* ``--no-session`` disables refinement *structurally*. Prime gates auto-refine
  on a session-local harness directory, so a sessionless run never refines no
  matter how ``autoRefine`` is configured. Sessions are therefore kept whenever
  refinement is expected, and only frozen runs stay sessionless.
* Prime ships ``turnInterval=25`` and a 20 minute cooldown, which never fire on
  a short benchmark episode. ``refine_turn_interval`` / ``refine_cooldown_ms``
  make that threshold an explicit experiment parameter rather than an
  assumption.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from harbor.agents.installed.base import BaseInstalledAgent, CliFlag, with_prompt_template
from harbor.agents.installed.node_install import nvm_node_install_snippet
from harbor.models.agent.context import AgentContext

INSTALL_URL = "https://app.primeintellect.ai/prime-agent/install.sh"
AGENT_DIR = "/tmp/prime-agent-dir"
KERNEL_VENV_DIR = "/tmp/prime-kernel-venv"
OUTPUT_FILENAME = "prime-agent.jsonl"
EXPORT_DIRNAME = "prime-agent-dir"
THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")
PROXY_ENV_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy")


class PrimeRuntimeMissingError(RuntimeError):
    pass


class PrimeAgent(BaseInstalledAgent):
    """Run Prime Agent against a Harbor task, optionally pinned to a harness."""

    CLI_FLAGS = [
        CliFlag("thinking", cli="--thinking", type="enum", choices=list(THINKING_LEVELS)),
    ]

    def __init__(
        self,
        *args: Any,
        auth_json_path: str | Path | None = None,
        harness_state_path: str | Path | None = None,
        agent_dir: str = AGENT_DIR,
        auto_refine: bool = False,
        refine_turn_interval: int | None = None,
        refine_cooldown_ms: int | None = None,
        runtime_prefix: str | None = None,
        kernel_venv_dir: str = KERNEL_VENV_DIR,
        install_url: str = INSTALL_URL,
        export_agent_dir: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._auth_json_path = Path(auth_json_path) if auth_json_path else None
        self._harness_state_path = Path(harness_state_path) if harness_state_path else None
        self._agent_dir = agent_dir
        self._auto_refine = auto_refine
        self._refine_turn_interval = refine_turn_interval
        self._refine_cooldown_ms = refine_cooldown_ms
        # Set to a mount point to skip the network install entirely; see
        # docs/guides/prime-agent.md for building the runtime bundle.
        self._runtime_prefix = runtime_prefix
        self._kernel_venv_dir = kernel_venv_dir
        self._install_url = install_url
        self._export_agent_dir = export_agent_dir

    @staticmethod
    def name() -> str:
        return "prime-agent"

    def get_version_command(self) -> str | None:
        # prime-agent prints its version on stderr; without the redirect Harbor
        # records the agent version as "unknown".
        return f"{self._path_export()} prime-agent --version 2>&1"

    def parse_version(self, stdout: str) -> str:
        return stdout.strip().splitlines()[-1].strip()

    def _path_export(self) -> str:
        prefix = f"{self._runtime_prefix}/bin:" if self._runtime_prefix else ""
        return f'. ~/.nvm/nvm.sh 2>/dev/null; export PATH="{prefix}$HOME/.local/bin:$PATH";'

    def _proxy_env(self) -> dict[str, str]:
        return {name: value for name in PROXY_ENV_NAMES if (value := self._get_env(name))}

    async def _install_from_runtime(self, environment) -> None:
        """Verify a pre-baked runtime mount instead of installing over the network."""
        prefix = shlex.quote(str(self._runtime_prefix))
        venv = shlex.quote(self._kernel_venv_dir)
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                f"test -x {prefix}/bin/prime-agent || "
                f'{{ echo "prime runtime missing at {self._runtime_prefix}" >&2; exit 1; }}; '
                # Prime bootstraps a lock beside the kernel venv, so it needs a
                # writable copy even when the runtime itself is mounted read-only.
                # Absolute paths inside the venv still resolve into the mount.
                f"if [ -d {prefix}/kernel-venv ] && [ ! -d {venv} ]; then "
                f"cp -a {prefix}/kernel-venv {venv}; fi; "
                f"{self._path_export()} prime-agent --version 2>&1"
            ),
        )

    async def install(self, environment) -> None:
        if self._runtime_prefix:
            await self._install_from_runtime(environment)
            return

        env = self._proxy_env()
        await self.exec_as_root(
            environment,
            command="apt-get update && apt-get install -y curl ca-certificates",
            env={"DEBIAN_FRONTEND": "noninteractive", **env},
        )
        # The installer runs `npm install -g` on the release tarball, so Node has
        # to exist first. Keep npm's prefix inside $HOME: agent users in task
        # images rarely own the system-wide prefix.
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                f"{nvm_node_install_snippet()} && "
                'export npm_config_prefix="$HOME/.local" && '
                'mkdir -p "$HOME/.local/bin" && '
                f"curl -fsSL {shlex.quote(self._install_url)} -o /tmp/prime-agent-install.sh && "
                "sh /tmp/prime-agent-install.sh && "
                'export PATH="$HOME/.local/bin:$PATH" && '
                "prime-agent --version 2>&1"
            ),
            env=env,
        )

    def _settings(self) -> dict[str, Any]:
        auto_refine: dict[str, Any] = {"enabled": self._auto_refine, "compact": self._auto_refine}
        if self._refine_turn_interval is not None:
            auto_refine["turnInterval"] = self._refine_turn_interval
        if self._refine_cooldown_ms is not None:
            auto_refine["cooldownMs"] = self._refine_cooldown_ms
        return {"autoRefine": auto_refine}

    async def _hydrate_agent_dir(self, environment) -> None:
        agent_dir = shlex.quote(self._agent_dir)
        await self.exec_as_agent(environment, command=f"mkdir -p {agent_dir}/harness")

        if self._auth_json_path is not None:
            if not self._auth_json_path.is_file():
                raise PrimeRuntimeMissingError(f"auth_json_path does not exist: {self._auth_json_path}")
            await environment.upload_file(self._auth_json_path, f"{self._agent_dir}/auth.json")

        settings = shlex.quote(json.dumps(self._settings(), indent=2))
        await self.exec_as_agent(
            environment,
            command=f"printf '%s' {settings} > {agent_dir}/settings.json",
        )

        if self._harness_state_path is not None:
            if not self._harness_state_path.is_file():
                raise PrimeRuntimeMissingError(f"harness_state_path does not exist: {self._harness_state_path}")
            await environment.upload_file(
                self._harness_state_path,
                f"{self._agent_dir}/harness/harness_state.json",
            )

    @with_prompt_template
    async def run(self, instruction: str, environment, context: AgentContext) -> None:
        provider, separator, model = (self.model_name or "").partition("/")
        if not separator or not provider or not model:
            raise ValueError("Model name must be in the format provider/model_name")

        await self._hydrate_agent_dir(environment)

        env = {**self._proxy_env(), "PRIME_AGENT_CODING_AGENT_DIR": self._agent_dir}
        if self._runtime_prefix:
            # Naming the interpreter is what skips auto-bootstrap. Pointing only
            # at the venv makes Prime re-check the runtime and demand `uv`, which
            # a task image will not have.
            env["PRIME_AGENT_KERNEL_PYTHON"] = f"{self._kernel_venv_dir}/bin/python"
            env["PRIME_AGENT_KERNEL_VENV"] = self._kernel_venv_dir
        for key in ("PRIME_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            if value := self._get_env(key):
                env[key] = value

        # A session is required for refinement to happen at all; a frozen run
        # stays sessionless so it cannot persist anything.
        session = f"--session-dir {shlex.quote(self._agent_dir)}/sessions" if self._auto_refine else "--no-session"
        cli_flags = self.build_cli_flags()

        await self.exec_as_agent(
            environment,
            command=(
                # `tee` is last in the pipeline, so without pipefail a crashed or
                # unauthenticated prime-agent still reports success and Harbor
                # scores the trial as a completed run.
                "set -o pipefail; "
                f"{self._path_export()} "
                f"prime-agent --print --mode json {session} "
                f"--provider {shlex.quote(provider)} --model {shlex.quote(model)} "
                f"{cli_flags + ' ' if cli_flags else ''}"
                f"{shlex.quote(instruction)} "
                f"2>&1 </dev/null | stdbuf -oL tee /logs/agent/{OUTPUT_FILENAME}"
            ),
            env=env,
        )

        if self._export_agent_dir:
            # Credentials must not outlive the trial: the export is a Harbor
            # artifact that gets retained and shared, so drop auth.json before
            # the directory leaves the container.
            await self.exec_as_agent(
                environment,
                command=f"rm -f {shlex.quote(self._agent_dir)}/auth.json",
            )
            # Captures harness_state.json plus anything the run persisted, so a
            # checkpoint chain can be rebuilt on the host afterwards.
            await environment.download_dir(self._agent_dir, self.logs_dir / EXPORT_DIRNAME)

    def populate_context_post_run(self, context: AgentContext) -> None:
        output_file = self.logs_dir / OUTPUT_FILENAME
        if not output_file.exists():
            return

        input_tokens = output_tokens = cache_read_tokens = 0
        total_cost = 0.0
        for line in output_file.read_text().splitlines():
            if not (line := line.strip()):
                continue
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if event.get("type") != "message_end":
                continue
            message = event.get("message") or {}
            if message.get("role") != "assistant":
                continue
            usage = message.get("usage") or {}
            input_tokens += usage.get("input", 0)
            output_tokens += usage.get("output", 0)
            cache_read_tokens += usage.get("cacheRead", 0)
            total_cost += (usage.get("cost") or {}).get("total", 0.0)

        context.n_input_tokens = input_tokens + cache_read_tokens
        context.n_output_tokens = output_tokens
        context.n_cache_tokens = cache_read_tokens
        context.cost_usd = total_cost if total_cost > 0 else None
