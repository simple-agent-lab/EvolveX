"""Harbor wrapper for the paper-poster Skill candidate."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from harbor.agents.installed.base import CliFlag
from harbor.agents.installed.codex import Codex
from harbor.environments.base import BaseEnvironment

TARGET_ROOT = Path(__file__).resolve().parent
REMOTE_SKILLS_DIR = "/tmp/evolve-target-skills"
VERIFIER_CODEX_HOME = "/tmp/evolve-verifier-codex-home"
DEFAULT_MODEL_SENTINEL = "__evolve_use_codex_default_model__"


def _settings() -> dict[str, Any]:
    with (TARGET_ROOT / "codex.toml").open("rb") as config_file:
        return tomllib.load(config_file)


def _table(settings: dict[str, Any], name: str) -> dict[str, Any]:
    value = settings.get(name)
    return value if isinstance(value, dict) else {}


class HarborAgent(Codex):
    """Codex with a candidate-owned paper-poster Skill."""

    CLI_FLAGS = [
        *Codex.CLI_FLAGS,
        CliFlag(
            "auto_compact_token_limit",
            cli="-c",
            type="int",
            format="-c model_auto_compact_token_limit={value}",
        ),
        CliFlag(
            "auto_compact_token_limit_scope",
            cli="-c",
            type="enum",
            choices=["total", "body_after_prefix"],
            format="-c model_auto_compact_token_limit_scope={value}",
        ),
        CliFlag(
            "tool_output_token_limit",
            cli="-c",
            type="int",
            format="-c tool_output_token_limit={value}",
        ),
    ]

    def __init__(self, logs_dir: Path, model_name: str | None = None, **kwargs: Any) -> None:
        settings = _settings()
        codex = _table(settings, "codex")
        skills = _table(settings, "skills")
        compaction = _table(settings, "compaction")

        self._skills_enabled = bool(skills.get("enabled", True))
        configured_model = str(codex.get("model") or "").strip() or None
        resolved_model = (
            model_name or os.environ.get("EVOLVE_HARBOR_MODEL") or os.environ.get("OPENAI_MODEL") or configured_model
        )

        kwargs.setdefault("version", str(codex.get("version") or "") or None)
        kwargs.setdefault("reasoning_effort", codex.get("reasoning_effort", "high"))
        kwargs.setdefault("reasoning_summary", codex.get("reasoning_summary", "auto"))
        kwargs.setdefault("web_search", codex.get("web_search", "disabled"))
        kwargs.setdefault("prompt_template_path", TARGET_ROOT / "prompt.md")
        kwargs.setdefault("skills_dir", REMOTE_SKILLS_DIR if self._skills_enabled else None)

        if compaction.get("override_defaults", False):
            kwargs.setdefault("auto_compact_token_limit", compaction.get("auto_compact_token_limit"))
            kwargs.setdefault(
                "auto_compact_token_limit_scope",
                compaction.get("auto_compact_token_limit_scope", "total"),
            )
            kwargs.setdefault("tool_output_token_limit", compaction.get("tool_output_token_limit"))

        super().__init__(logs_dir=logs_dir, model_name=resolved_model, **kwargs)

    def _resolve_auth_json_path(self) -> Path:
        configured = self._get_env("CODEX_AUTH_JSON_PATH")
        codex_home = Path(self._get_env("CODEX_HOME") or Path.home() / ".codex")
        auth_path = Path(configured).expanduser() if configured else codex_home / "auth.json"
        if not auth_path.is_file():
            raise ValueError(f"Codex auth.json does not exist: {auth_path}")
        return auth_path

    def _candidate_root(self) -> Path:
        source = self._get_env("EVOLVE_CANDIDATE_SOURCE") or os.environ.get("EVOLVE_CANDIDATE_SOURCE")
        return Path(source).expanduser().resolve() if source else TARGET_ROOT

    async def exec_as_agent(
        self,
        environment: BaseEnvironment,
        command: str,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout_sec: int | None = None,
    ) -> Any:
        command = command.replace(f"--model {DEFAULT_MODEL_SENTINEL} ", "", 1)
        marker = "codex exec "
        if marker in command and "--dangerously-bypass-hook-trust" not in command:
            command = command.replace(marker, marker + "--dangerously-bypass-hook-trust ", 1)
        return await super().exec_as_agent(
            environment,
            command=command,
            env=env,
            cwd=cwd,
            timeout_sec=timeout_sec,
        )

    async def run(self, instruction: str, environment: BaseEnvironment, context: Any) -> None:
        if self.model_name:
            await super().run(instruction, environment, context)
            return
        # Harbor's installed Codex adapter requires a model name, while Codex
        # itself selects its configured default when --model is omitted.
        self.model_name = DEFAULT_MODEL_SENTINEL
        try:
            await super().run(instruction, environment, context)
        finally:
            self.model_name = None

    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        await self.exec_as_agent(
            environment,
            command=f"mkdir -p {VERIFIER_CODEX_HOME} && chmod 700 {VERIFIER_CODEX_HOME}",
        )
        await environment.upload_file(
            source_path=self._resolve_auth_json_path(),
            target_path=f"{VERIFIER_CODEX_HOME}/auth.json",
        )
        skills = self._candidate_root() / "skills"
        if not self._skills_enabled or not skills.is_dir():
            return
        await self.exec_as_agent(environment, command=f"mkdir -p {REMOTE_SKILLS_DIR}")
        await environment.upload_dir(source_dir=skills, target_dir=REMOTE_SKILLS_DIR)
