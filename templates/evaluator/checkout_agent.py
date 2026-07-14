#!/usr/bin/env python3
from __future__ import annotations

import os
from importlib import import_module
from pathlib import Path, PurePosixPath
from typing import cast

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

_FORWARDED_ENV_KEYS = (
    "API_KIND CODEX_AUTH_JSON_PATH CODEX_FORCE_AUTH_JSON EVOLVE_HARBOR_MODEL "
    "EVOLVE_LLM_API_KEY EVOLVE_LLM_BASE_URL EVOLVE_LLM_MODEL "
    "MSWEA_API_KEY OPENAI_API_BASE OPENAI_API_KEY OPENAI_AUTH_TOKEN "
    "OPENAI_BASE_URL OPENAI_MODEL http_proxy https_proxy no_proxy "
    "HTTP_PROXY HTTPS_PROXY NO_PROXY"
).split()


def _forwarded_env() -> dict[str, str]:
    return {key: value for key in _FORWARDED_ENV_KEYS if (value := os.environ.get(key))}


def _load_delegate(logs_dir: Path, model_name: str | None, extra_env: dict[str, str]) -> BaseAgent | None:
    candidates = (
        ("target.harbor_agent", "HarborAgent"),
        ("target.agent", "HarborAgent"),
        ("target.agent", "TargetAgent"),
        ("target.agent", "Agent"),
    )
    for module_name, class_name in candidates:
        try:
            module = import_module(module_name)
            candidate = getattr(module, class_name)
        except (ImportError, AttributeError):
            continue
        if not isinstance(candidate, type) or not issubclass(candidate, BaseAgent) or candidate is CheckoutTargetAgent:
            continue
        return cast(BaseAgent, candidate(logs_dir=logs_dir, model_name=model_name, extra_env=extra_env))
    return None


def _target_command() -> tuple[str, dict[str, str]]:
    host_root = Path("target")
    container_root = PurePosixPath("/tmp/evolve-target")
    candidates = (
        ("target/solve.sh", "sh"),
        ("target/run.sh", "sh"),
        ("target/agent.sh", "sh"),
        ("target/agent.py", "python3"),
        ("target/run.py", "python3"),
        ("target/main.py", "python3"),
    )
    for relative, launcher in candidates:
        path = Path(relative)
        if not path.exists():
            continue
        container_path = container_root / path.relative_to(host_root).as_posix()
        return f"{launcher} {container_path.as_posix()}", {"EVOLVE_TARGET_DIR": container_root.as_posix()}
    raise RuntimeError(
        "No conventional target entrypoint found under target/. Expected one of: "
        "target/solve.sh, target/run.sh, target/agent.sh, target/agent.py, target/run.py, target/main.py."
    )


class CheckoutTargetAgent(BaseAgent):
    SUPPORTS_WINDOWS = True

    @staticmethod
    def name() -> str:
        return "evolve-checkout-target"

    def version(self) -> str:
        return "0.1.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        delegate = _load_delegate(self.logs_dir, self.model_name, {**_forwarded_env(), **self.extra_env})
        if delegate is not None:
            await delegate.setup(environment)
            return
        await environment.upload_dir(source_dir=Path("target"), target_dir="/tmp/evolve-target")

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        delegate = _load_delegate(self.logs_dir, self.model_name, {**_forwarded_env(), **self.extra_env})
        if delegate is not None:
            await delegate.run(instruction, environment, context)
            return
        command, extra_env = _target_command()
        result = await environment.exec(
            command=command,
            env={**_forwarded_env(), **self.extra_env, **extra_env, "EVOLVE_INSTRUCTION": instruction},
        )
        (self.logs_dir / "checkout-target.stdout.txt").write_text(result.stdout or "")
        (self.logs_dir / "checkout-target.stderr.txt").write_text(result.stderr or "")
        if result.return_code != 0:
            raise RuntimeError(f"checkout target command failed with exit code {result.return_code}")
