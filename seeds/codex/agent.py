"""Evolvable Harbor wrapper around the installed Codex CLI agent."""

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


def _settings() -> dict[str, Any]:
    with (TARGET_ROOT / "codex.toml").open("rb") as config_file:
        return tomllib.load(config_file)


def _table(settings: dict[str, Any], name: str) -> dict[str, Any]:
    value = settings.get(name)
    return value if isinstance(value, dict) else {}


class HarborAgent(Codex):
    """Codex with candidate-owned prompt, skills, and context policy."""

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
        configured_model = str(codex.get("model") or "gpt-5.4")
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

    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        skills = TARGET_ROOT / "skills"
        if self._skills_enabled and skills.is_dir():
            await environment.upload_dir(source_dir=skills, target_dir=REMOTE_SKILLS_DIR)

    async def run(self, instruction: str, environment, context) -> None:
        if self._get_env("EVOLVE_CANDIDATE_SMOKE_MODE") == "model":
            instruction = "Reply with exactly OK. Do not use tools."
        await super().run(instruction, environment, context)
