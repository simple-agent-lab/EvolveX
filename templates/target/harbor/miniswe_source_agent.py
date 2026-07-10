from __future__ import annotations

import shlex
import shutil
from pathlib import Path

from harbor.agents.installed.mini_swe_agent import MiniSweAgent


SOURCE_DIR = "/installed-agent/miniswe-source"
RUNNER_PATH = "/tmp/miniswe-source-run.py"
TASK_PATH = "/tmp/miniswe-source-task.txt"
LOG_PATH = "/logs/agent/mini-swe-agent.txt"
HOST_UV_PATH = "/tmp/evolve-uv"


RUNNER = r'''
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
'''.strip()


class MiniSweSourceAgent(MiniSweAgent):
    async def install(self, environment):
        source_dir = Path(__file__).resolve().parent
        if not (source_dir / "pyproject.toml").is_file():
            raise RuntimeError("MiniSWE source target must contain target/pyproject.toml")
        if not ((source_dir / "src" / "minisweagent").is_dir() or (source_dir / "minisweagent").is_dir()):
            raise RuntimeError("MiniSWE source target must contain target/src/minisweagent/")
        await environment.upload_dir(source_dir, SOURCE_DIR)
        host_uv = self._host_uv_binary()
        if host_uv is not None:
            await environment.upload_file(host_uv, HOST_UV_PATH)
        install_env = self._install_env()
        if hasattr(self, "exec_as_root"):
            await self.exec_as_root(
                environment,
                command=(
                    "if command -v apt-get &>/dev/null; then "
                    "apt-get update && apt-get install -y curl build-essential git python3; "
                    "elif command -v apk &>/dev/null; then "
                    "apk add --no-cache curl bash build-base git python3 py3-pip; "
                    "elif command -v yum &>/dev/null; then "
                    "yum install -y curl git gcc make python3; "
                    "elif command -v dnf &>/dev/null; then "
                    "dnf install -y curl git gcc make python3; "
                    "fi"
                ),
                env={**install_env, "DEBIAN_FRONTEND": "noninteractive"},
            )
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                "mkdir -p \"$HOME/.local/bin\"; export PATH=\"$HOME/.local/bin:$PATH\"; "
                f"if [ -f {HOST_UV_PATH} ]; then "
                f"cp {HOST_UV_PATH} \"$HOME/.local/bin/uv\"; chmod 755 \"$HOME/.local/bin/uv\"; "
                "if ! \"$HOME/.local/bin/uv\" --version >/dev/null 2>&1; then rm -f \"$HOME/.local/bin/uv\"; fi; "
                "fi; "
                "if ! command -v uv >/dev/null 2>&1 || ! uv --version >/dev/null 2>&1; then "
                "rm -f \"$HOME/.local/bin/uv\"; "
                "curl -LsSf https://astral.sh/uv/0.7.13/install.sh | sh; "
                "fi; "
                "if [ -f \"$HOME/.local/bin/env\" ]; then . \"$HOME/.local/bin/env\"; "
                "else export PATH=\"$HOME/.local/bin:$PATH\"; fi; "
                f"uv run --project {SOURCE_DIR} python -c "
                "\"import minisweagent; from minisweagent.agents.default import DefaultAgent; "
                "print('miniswe-source-ok')\""
            ),
            env=install_env,
        )

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
        env: dict[str, str] = {}
        proxy = (
            self._get_env("EVOLVE_INSTALL_HTTP_PROXY")
            or self._get_env("EVOLVE_DOCKER_HTTP_PROXY")
            or self._get_env("http_proxy")
            or self._get_env("HTTP_PROXY")
        )
        if proxy is not None:
            env.update({"http_proxy": proxy, "https_proxy": proxy, "HTTP_PROXY": proxy, "HTTPS_PROXY": proxy})
        no_proxy = self._get_env("EVOLVE_INSTALL_NO_PROXY") or self._get_env("no_proxy") or self._get_env("NO_PROXY")
        if no_proxy is not None:
            env.update({"no_proxy": no_proxy, "NO_PROXY": no_proxy})
        return env

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
            "if [ -f \"$HOME/.local/bin/env\" ]; then . \"$HOME/.local/bin/env\"; "
            "else export PATH=\"$HOME/.local/bin:$PATH\"; fi\n"
            "unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy\n"
            f"cat > {shlex.quote(RUNNER_PATH)} <<'PY'\n{RUNNER}\nPY\n"
            "python - <<'PY'\n"
            "from pathlib import Path\n"
            f"Path({TASK_PATH!r}).write_text({task_literal})\n"
            "PY\n"
            f"uv run --project {shlex.quote(SOURCE_DIR)} python {shlex.quote(RUNNER_PATH)} "
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
        return env
