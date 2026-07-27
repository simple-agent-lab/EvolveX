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
PROXY_ENV_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy")


class EvolveCandidateInvalidError(RuntimeError):
    pass


class EvolveRuntimeInfrastructureError(RuntimeError):
    pass


MODEL_SETUP = r"""
import json
import os
import uuid
from minisweagent.models.litellm_model import LitellmModel, LitellmModelConfig
from minisweagent.models.litellm_response_model import LitellmResponseModel

VALID_REASONING_EFFORTS = ("none", "low", "medium", "high", "xhigh")


def _filtered(values, allowed):
    return {key: value for key, value in (values or {}).items() if key in allowed}


def _reasoning_effort():
    effort = os.environ.get("MINISWE_REASONING_EFFORT", "").strip().lower()
    if not effort:
        return None
    if effort not in VALID_REASONING_EFFORTS:
        accepted = ", ".join(VALID_REASONING_EFFORTS)
        raise ValueError(
            f"Invalid MINISWE_REASONING_EFFORT={effort!r}; expected one of: {accepted}"
        )
    return effort


def build_model(config):
    model_name = os.environ["MSWEA_MODEL_NAME"]
    effort = _reasoning_effort()
    model_kwargs = _filtered(config.get("model"), LitellmModelConfig.model_fields)
    model_kwargs["model_name"] = model_name
    model_kwargs["cost_tracking"] = "ignore_errors"

    if model_name.startswith("openai/"):
        nested_kwargs = dict(model_kwargs.get("model_kwargs") or {})
        nested_kwargs.setdefault("max_output_tokens", 64_000)
        nested_kwargs.pop("reasoning_effort", None)
        if effort is not None:
            nested_kwargs["reasoning"] = {"effort": effort}
        include = list(nested_kwargs.get("include") or [])
        if "reasoning.encrypted_content" not in include:
            include.append("reasoning.encrypted_content")
        nested_kwargs["include"] = include
        cache_key = f"evolve-{uuid.uuid4().hex}"
        nested_kwargs["prompt_cache_key"] = cache_key
        extra_headers = dict(nested_kwargs.get("extra_headers") or {})
        extra_headers["extra"] = json.dumps({"session_id": cache_key}, separators=(",", ":"))
        nested_kwargs["extra_headers"] = extra_headers
        model_kwargs["model_kwargs"] = nested_kwargs
        return LitellmResponseModel(**model_kwargs)

    return LitellmModel(**model_kwargs)
""".strip()


EVOLVED_CONTEXT_SETUP = r"""
import json
from pathlib import Path

import yaml


def _load_evolved_context(source_dir):
    source_root = Path(source_dir)
    skills = []
    skills_dir = source_root / "skills"
    if skills_dir.is_dir():
        for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
            if skill_file.parent.name.startswith("_"):
                continue
            text = skill_file.read_text()
            metadata = {}
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) == 3:
                    metadata = yaml.safe_load(parts[1]) or {}
                    if not isinstance(metadata, dict):
                        raise ValueError(f"Skill frontmatter must be a mapping: {skill_file}")
            skills.append(
                {
                    "name": str(metadata.get("name") or skill_file.parent.name),
                    "description": str(metadata.get("description") or "").strip(),
                    "path": skill_file,
                }
            )

    memories = []
    memory_dir = source_root / "memory"
    if memory_dir.is_dir():
        for memory_file in sorted(memory_dir.glob("*.jsonl")):
            for line_number, line in enumerate(memory_file.read_text().splitlines(), 1):
                if not line.strip():
                    continue
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    raise ValueError(f"Memory entry must be an object: {memory_file}:{line_number}")
                memories.append(entry)
    memories = memories[-100:]

    sections = []
    if skills:
        lines = [
            "## Available Skills",
            "",
            "Reusable procedures are available below. Before a relevant task, use the bash tool to read the "
            "referenced `SKILL.md` file and follow its full procedure.",
        ]
        for skill in skills:
            description = f": {skill['description']}" if skill["description"] else ""
            lines.append(f"- **{skill['name']}**{description} (file: `{skill['path']}`)")
        sections.append("\n".join(lines))
    if memories:
        lines = [
            "## Evolved Memory",
            "",
            "These are transferable observations retained from earlier task trajectories. Apply them only when "
            "relevant to the current task.",
        ]
        lines.extend(f"- {json.dumps(entry, ensure_ascii=False, sort_keys=True)}" for entry in memories)
        sections.append("\n".join(lines))
    text = "\n\n".join(sections)
    return text, {"skills_loaded": len(skills), "memories_loaded": len(memories)}


def _apply_evolved_context(agent_kwargs, source_dir):
    context, stats = _load_evolved_context(source_dir)
    if context:
        system_template = str(agent_kwargs.get("system_template") or "").rstrip()
        agent_kwargs["system_template"] = f"{system_template}\n\n{context}\n"
    return stats
""".strip()


RUNNER = (
    MODEL_SETUP
    + "\n\n"
    + EVOLVED_CONTEXT_SETUP
    + r"""
import json
from pathlib import Path

from minisweagent.agents.default import AgentConfig, DefaultAgent
from minisweagent.config import get_config_from_spec
from minisweagent.environments.local import LocalEnvironment, LocalEnvironmentConfig


task = Path(os.environ["MINISWE_TASK_PATH"]).read_text()
config = get_config_from_spec(os.environ.get("MINISWE_CONFIG", "mini"))
agent_kwargs = _filtered(config.get("agent"), AgentConfig.model_fields)
_apply_evolved_context(agent_kwargs, "/installed-agent/miniswe-source")
env_kwargs = _filtered(config.get("environment"), LocalEnvironmentConfig.model_fields)
env_kwargs["cwd"] = os.environ.get("MINISWE_CWD") or os.getcwd()
env_kwargs["timeout"] = int(os.environ.get("MINISWE_ENV_TIMEOUT", env_kwargs.get("timeout") or 30))
agent_kwargs["step_limit"] = int(os.environ.get("MINISWE_STEP_LIMIT", agent_kwargs.get("step_limit") or 0))
agent_kwargs["cost_limit"] = float(os.environ.get("MINISWE_COST_LIMIT", agent_kwargs.get("cost_limit") or 0))
agent_kwargs["output_path"] = os.environ.get("MINISWE_OUTPUT_PATH")
model = build_model(config)
agent = DefaultAgent(model, LocalEnvironment(**env_kwargs), **agent_kwargs)
print(json.dumps(agent.run(task), default=str))
"""
).strip()


MINISWE_PREFLIGHT = (
    EVOLVED_CONTEXT_SETUP
    + "\n\n"
    + r"""
from minisweagent.agents.default import DefaultAgent
from minisweagent.config import get_config_from_spec
from minisweagent.environments.local import LocalEnvironment

assert DefaultAgent and LocalEnvironment and get_config_from_spec
_load_evolved_context("/installed-agent/miniswe-source")
print("EVOLVE_PREFLIGHT: miniswe_import_ok")
"""
).strip()


MODEL_PREFLIGHT = (
    MODEL_SETUP
    + r"""
from minisweagent.config import get_config_from_spec

config = get_config_from_spec(os.environ.get("MINISWE_CONFIG", "mini"))
build_model(config)
print("EVOLVE_PREFLIGHT: model_path_init_ok")
"""
).strip()


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
        offline_runtime = self._get_env("UV_OFFLINE") == "1"
        missing_uv = (
            'printf "EVOLVE_UV_BOOTSTRAP_MISSING\\n" >&2; false; '
            if offline_runtime
            else "curl -LsSf https://astral.sh/uv/0.7.13/install.sh | sh; "
        )
        await self._runtime_phase(
            environment,
            command=(
                "set -euo pipefail; "
                'mkdir -p "$HOME/.local/bin"; export PATH="$HOME/.local/bin:$PATH"; '
                "if ! command -v uv >/dev/null 2>&1 || ! uv --version >/dev/null 2>&1; then "
                f"if [ -f {HOST_UV_PATH} ]; then "
                f'cp {HOST_UV_PATH} "$HOME/.local/bin/uv"; chmod 755 "$HOME/.local/bin/uv"; '
                'if ! "$HOME/.local/bin/uv" --version >/dev/null 2>&1; then rm -f "$HOME/.local/bin/uv"; fi; '
                "fi; "
                "fi; "
                "if ! command -v uv >/dev/null 2>&1 || ! uv --version >/dev/null 2>&1; then "
                'rm -f "$HOME/.local/bin/uv"; '
                f"{missing_uv}"
                "fi; "
                'if [ -f "$HOME/.local/bin/env" ]; then . "$HOME/.local/bin/env"; '
                'else export PATH="$HOME/.local/bin:$PATH"; fi; '
                "uv --version >/dev/null"
            ),
            code="uv_bootstrap_failed",
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
        except Exception as error:
            raise EvolveRuntimeInfrastructureError(f"EVOLVE_RUNTIME_INFRASTRUCTURE: {code}: {error}") from None

    def _preflight_command(self, marker: str, script: str) -> str:
        return (
            "set -euo pipefail; "
            f"echo {shlex.quote(marker)} >/dev/null; "
            f"{VENV_PYTHON} -c {shlex.quote(script)}"
        )

    def _runtime_evidence_command(self) -> str:
        mode = self._get_env("EVOLVE_CANDIDATE_SMOKE_MODE") or "normal"
        payload = json.dumps(
            {
                "schema_version": 1,
                "mode": mode,
                "frozen_sync": True,
                "miniswe_import": True,
                "model_path_init": mode != "container",
            },
            sort_keys=True,
        )
        script = (
            EVOLVED_CONTEXT_SETUP
            + "\n"
            + f"context, stats = _load_evolved_context({SOURCE_DIR!r})\n"
            + f"payload = json.loads({payload!r})\n"
            + "payload.update(stats)\n"
            + "payload['context_chars'] = len(context)\n"
            + f"Path({RUNTIME_EVIDENCE_PATH!r}).write_text(json.dumps(payload, sort_keys=True) + '\\n')"
        )
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
        env = {
            "UV_CACHE_DIR": self._get_env("UV_CACHE_DIR") or UV_CACHE_DIR,
            "UV_LINK_MODE": self._get_env("UV_LINK_MODE") or "copy",
            "UV_OFFLINE": self._get_env("UV_OFFLINE") or "1",
            "UV_PYTHON_INSTALL_DIR": self._get_env("UV_PYTHON_INSTALL_DIR") or UV_PYTHON_INSTALL_DIR,
        }
        env.update(self._proxy_env())
        return env

    def _proxy_env(self) -> dict[str, str]:
        return {
            name: value
            for name in PROXY_ENV_NAMES
            if (value := self._get_env(name)) is not None
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
        env.update(self._proxy_env())
        for name in (
            "MINISWE_STEP_LIMIT",
            "MINISWE_COST_LIMIT",
            "MINISWE_ENV_TIMEOUT",
            "MINISWE_REASONING_EFFORT",
        ):
            value = self._get_env(name)
            if value is not None:
                env[name] = value
        smoke_mode = self._get_env("EVOLVE_CANDIDATE_SMOKE_MODE")
        if smoke_mode is not None:
            env["EVOLVE_CANDIDATE_SMOKE_MODE"] = smoke_mode
        return env
