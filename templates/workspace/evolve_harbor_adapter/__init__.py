from __future__ import annotations

import json
import shlex
import shutil
from pathlib import Path

from harbor.agents.installed.mini_swe_agent import MiniSweAgent

SOURCE_DIR = "/installed-agent/miniswe-source"
VENV_PYTHON = f"{SOURCE_DIR}/.venv/bin/python"
UV_CACHE_DIR = "/opt/evolve/uv/cache"
UV_PYTHON_INSTALL_DIR = "/opt/evolve/uv/python"
RUNNER_PATH = "/tmp/miniswe-source-run.py"
TASK_PATH = "/tmp/miniswe-source-task.txt"
LOG_PATH = "/logs/agent/mini-swe-agent.txt"
RUNTIME_EVIDENCE_PATH = "/logs/agent/evolve-runtime.json"
HOST_UV_PATH = "/tmp/evolve-uv"
PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


class EvolveCandidateInvalidError(RuntimeError):
    pass


class EvolveRuntimeInfrastructureError(RuntimeError):
    pass


RUNNER = r"""
import json
import os
from pathlib import Path

from minisweagent.agents.default import AgentConfig, DefaultAgent
from minisweagent.config import get_config_from_spec
from minisweagent.environments.local import LocalEnvironment, LocalEnvironmentConfig
from minisweagent.models.litellm_model import LitellmModel, LitellmModelConfig


def filtered(payload, fields):
    return {key: value for key, value in dict(payload or {}).items() if key in fields}


task = Path(os.environ["MINISWE_TASK_PATH"]).read_text()
config = get_config_from_spec(os.environ.get("MINISWE_CONFIG", "mini"))
agent_kwargs = filtered(config.get("agent"), AgentConfig.model_fields)
env_kwargs = filtered(config.get("environment"), LocalEnvironmentConfig.model_fields)
model_kwargs = filtered(config.get("model"), LitellmModelConfig.model_fields)
model_kwargs["model_name"] = os.environ["MSWEA_MODEL_NAME"]
model_kwargs["cost_tracking"] = "ignore_errors"
env_kwargs["cwd"] = os.environ.get("MINISWE_CWD", "/app")
env_kwargs["timeout"] = int(os.environ.get("MINISWE_ENV_TIMEOUT", env_kwargs.get("timeout") or 30))
agent_kwargs["step_limit"] = int(os.environ.get("MINISWE_STEP_LIMIT", agent_kwargs.get("step_limit") or 0))
agent_kwargs["cost_limit"] = float(os.environ.get("MINISWE_COST_LIMIT", agent_kwargs.get("cost_limit") or 0))
agent_kwargs["output_path"] = os.environ.get("MINISWE_OUTPUT_PATH")
agent = DefaultAgent(LitellmModel(**model_kwargs), LocalEnvironment(**env_kwargs), **agent_kwargs)
print(json.dumps(agent.run(task), default=str))
""".strip()


MINISWE_PREFLIGHT = r"""
from minisweagent.agents.default import DefaultAgent
from minisweagent.config import get_config_from_spec
from minisweagent.environments.local import LocalEnvironment

assert DefaultAgent and LocalEnvironment and get_config_from_spec
print("EVOLVE_PREFLIGHT: miniswe_import_ok")
""".strip()


MODEL_PREFLIGHT = r"""
import os

from minisweagent.config import get_config_from_spec
from minisweagent.models.litellm_model import LitellmModel, LitellmModelConfig

config = get_config_from_spec(os.environ.get("MINISWE_CONFIG", "mini"))
model_kwargs = {
    key: value
    for key, value in dict(config.get("model") or {}).items()
    if key in LitellmModelConfig.model_fields
}
model_kwargs["model_name"] = os.environ["MSWEA_MODEL_NAME"]
model_kwargs["cost_tracking"] = "ignore_errors"
LitellmModel(**model_kwargs)
print("EVOLVE_PREFLIGHT: model_path_init_ok")
""".strip()


class MiniSweSourceAgent(MiniSweAgent):
    async def install(self, environment):
        source = self._get_env("EVOLVE_CANDIDATE_SOURCE")
        if not source:
            raise EvolveCandidateInvalidError("EVOLVE_CANDIDATE_INVALID: candidate_source_missing")
        source_dir = Path(source).expanduser().resolve()
        if not (source_dir / "pyproject.toml").is_file():
            raise EvolveCandidateInvalidError("EVOLVE_CANDIDATE_INVALID: project_missing")
        if not (source_dir / "uv.lock").is_file():
            raise EvolveCandidateInvalidError("EVOLVE_CANDIDATE_INVALID: lock_missing")
        if not ((source_dir / "src" / "minisweagent").is_dir() or (source_dir / "minisweagent").is_dir()):
            raise EvolveCandidateInvalidError("EVOLVE_CANDIDATE_INVALID: source_missing")
        await environment.upload_dir(source_dir, SOURCE_DIR)
        host_uv = self._host_uv_binary()
        if host_uv is not None:
            await environment.upload_file(host_uv, HOST_UV_PATH)
        install_env = self._install_env()
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                'mkdir -p "$HOME/.local/bin"; export PATH="$HOME/.local/bin:$PATH"; '
                f"if [ -f {HOST_UV_PATH} ]; then "
                f'cp {HOST_UV_PATH} "$HOME/.local/bin/uv"; chmod 755 "$HOME/.local/bin/uv"; '
                'if ! "$HOME/.local/bin/uv" --version >/dev/null 2>&1; then rm -f "$HOME/.local/bin/uv"; fi; '
                "fi; "
                "if ! command -v uv >/dev/null 2>&1 || ! uv --version >/dev/null 2>&1; then "
                'rm -f "$HOME/.local/bin/uv"; '
                "curl -LsSf https://astral.sh/uv/0.7.13/install.sh | sh; "
                "fi; "
                'if [ -f "$HOME/.local/bin/env" ]; then . "$HOME/.local/bin/env"; '
                'else export PATH="$HOME/.local/bin:$PATH"; fi; '
                "uv --version >/dev/null"
            ),
            env=install_env,
        )
        await self._runtime_phase(
            environment,
            "set -euo pipefail; "
            'if [ -f "$HOME/.local/bin/env" ]; then . "$HOME/.local/bin/env"; '
            'else export PATH="$HOME/.local/bin:$PATH"; fi; '
            f"uv sync --project {SOURCE_DIR} --frozen --no-install-local --offline",
            "external_dependency_sync_failed",
            env=install_env,
        )
        await self._candidate_phase(
            environment,
            "set -euo pipefail; "
            'if [ -f "$HOME/.local/bin/env" ]; then . "$HOME/.local/bin/env"; '
            'else export PATH="$HOME/.local/bin:$PATH"; fi; '
            f"uv sync --project {SOURCE_DIR} --frozen --offline",
            "local_project_sync_failed",
            env=install_env,
        )
        await self._candidate_phase(
            environment,
            self._preflight_command("EVOLVE_PREFLIGHT_MINISWE", MINISWE_PREFLIGHT),
            "miniswe_import_failed",
            env=self._source_env(),
        )
        if self._get_env("EVOLVE_CANDIDATE_SMOKE_MODE") != "container":
            await self._candidate_phase(
                environment,
                self._preflight_command("EVOLVE_PREFLIGHT_MODEL", MODEL_PREFLIGHT),
                "model_path_import_failed",
                env=self._source_env(),
            )
        await self.exec_as_agent(
            environment,
            command=self._runtime_evidence_command(),
            env=self._source_env(),
        )

    async def _candidate_phase(self, environment, command: str, code: str, *, env: dict[str, str]) -> None:
        try:
            await self.exec_as_agent(environment, command=command, env=env)
        except Exception:
            raise EvolveCandidateInvalidError(f"EVOLVE_CANDIDATE_INVALID: {code}") from None

    async def _runtime_phase(self, environment, command: str, code: str, *, env: dict[str, str]) -> None:
        try:
            await self.exec_as_agent(environment, command=command, env=env)
        except Exception:
            raise EvolveRuntimeInfrastructureError(code) from None

    def _preflight_command(self, marker: str, script: str) -> str:
        return (
            "set -euo pipefail; "
            f"unset {' '.join(PROXY_NAMES)}; "
            f"echo {shlex.quote(marker)} >/dev/null; "
            f"{VENV_PYTHON} -c {shlex.quote(script)}"
        )

    def _runtime_evidence_command(self) -> str:
        mode = self._get_env("EVOLVE_CANDIDATE_SMOKE_MODE") or "normal"
        payload = (
            json.dumps(
                {
                    "schema_version": 1,
                    "mode": mode,
                    "frozen_sync": True,
                    "miniswe_import": True,
                    "model_path_init": mode != "container",
                },
                sort_keys=True,
            )
            + "\n"
        )
        script = f"from pathlib import Path; Path({RUNTIME_EVIDENCE_PATH!r}).write_text({payload!r})"
        return f"mkdir -p /logs/agent; {VENV_PYTHON} -c {shlex.quote(script)}"

    def _host_uv_binary(self) -> Path | None:
        candidates = [self._get_env("EVOLVE_UV_BINARY") or "", shutil.which("uv") or ""]
        for candidate in candidates:
            path = Path(candidate).expanduser()
            if path.is_file():
                return path
        return None

    async def run(self, instruction: str, environment, context) -> None:
        if not self.model_name or "/" not in self.model_name:
            raise ValueError("Model name must be in the format provider/model_name")
        task = self._augment_instruction(instruction)
        await self.exec_as_agent(environment, command=self._run_command(task), env=self._source_env())

    def _install_env(self) -> dict[str, str]:
        return {
            "UV_CACHE_DIR": self._get_env("UV_CACHE_DIR") or UV_CACHE_DIR,
            "UV_LINK_MODE": self._get_env("UV_LINK_MODE") or "copy",
            "UV_OFFLINE": self._get_env("UV_OFFLINE") or "1",
            "UV_PYTHON_INSTALL_DIR": self._get_env("UV_PYTHON_INSTALL_DIR") or UV_PYTHON_INSTALL_DIR,
        }

    def _augment_instruction(self, instruction: str) -> str:
        if not getattr(self, "mcp_servers", None):
            return instruction
        mcp_info = "\n\nMCP Servers:\nThe following MCP servers are available for this task.\n"
        for server in self.mcp_servers:
            if server.transport == "stdio":
                mcp_info += f"- {server.name}: stdio transport, command: {server.command} {' '.join(server.args)}\n"
            else:
                mcp_info += f"- {server.name}: {server.transport} transport, url: {server.url}\n"
        return instruction + mcp_info

    def _run_command(self, task: str) -> str:
        task_literal = repr(task)
        return (
            "set -euo pipefail\n"
            'if [ -f "$HOME/.local/bin/env" ]; then . "$HOME/.local/bin/env"; '
            'else export PATH="$HOME/.local/bin:$PATH"; fi\n'
            "unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy\n"
            f"cat > {shlex.quote(RUNNER_PATH)} <<'PY'\n{RUNNER}\nPY\n"
            f"{VENV_PYTHON} - <<'PY'\n"
            "from pathlib import Path\n"
            f"Path({TASK_PATH!r}).write_text({task_literal})\n"
            "PY\n"
            f"{VENV_PYTHON} {shlex.quote(RUNNER_PATH)} "
            f"2>&1 </dev/null | tee {shlex.quote(LOG_PATH)}"
        )

    def _source_env(self) -> dict[str, str]:
        env = {
            "MSWEA_CONFIGURED": "true",
            "MSWEA_COST_TRACKING": "ignore_errors",
            "MSWEA_MODEL_NAME": self.model_name,
            "MINISWE_TASK_PATH": TASK_PATH,
            "MINISWE_OUTPUT_PATH": str(self._mini_swe_agent_trajectory_path),
        }
        for name in ("MSWEA_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            value = self._get_env(name)
            if value is not None:
                env[name] = value
        api_base = self._get_env("OPENAI_BASE_URL") or self._get_env("OPENAI_API_BASE")
        if api_base is not None:
            env["OPENAI_BASE_URL"] = api_base
            env["OPENAI_API_BASE"] = api_base
        for name in ("MINISWE_STEP_LIMIT", "MINISWE_COST_LIMIT", "MINISWE_ENV_TIMEOUT"):
            value = self._get_env(name)
            if value is not None:
                env[name] = value
        smoke_mode = self._get_env("EVOLVE_CANDIDATE_SMOKE_MODE")
        if smoke_mode is not None:
            env["EVOLVE_CANDIDATE_SMOKE_MODE"] = smoke_mode
        return env
