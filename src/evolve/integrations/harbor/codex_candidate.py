"""Codex Harbor adapters for OpenAI-compatible Responses endpoints."""

from __future__ import annotations

import shlex
import shutil
from pathlib import Path

from harbor.agents.installed.codex import Codex


class ResponsesCodexAgent(Codex):
    """Codex adapter for an OpenAI-compatible HTTP Responses endpoint."""

    async def install(self, environment) -> None:
        local_codex = shutil.which("codex")
        if local_codex:
            remote_codex = "/tmp/evolve-host-codex"
            await environment.upload_file(Path(local_codex).resolve(), remote_codex)
            await self.exec_as_root(
                environment,
                command=f"install -m 755 {shlex.quote(remote_codex)} /usr/local/bin/codex",
            )
        await super().install(environment)

    def build_cli_flags(self) -> str:
        base_url = self._get_env("OPENAI_BASE_URL") or self._get_env("OPENAI_API_BASE")
        if not base_url:
            raise ValueError("ResponsesCodexAgent requires OPENAI_BASE_URL or OPENAI_API_BASE")
        if not self._get_env("OPENAI_API_KEY"):
            raise ValueError("ResponsesCodexAgent requires OPENAI_API_KEY")
        configs = [
            'model_provider="evolve_http"',
            'forced_login_method="api"',
            'model_providers.evolve_http.name="EvolveX HTTP Responses"',
            f'model_providers.evolve_http.base_url="{base_url}"',
            'model_providers.evolve_http.env_key="OPENAI_API_KEY"',
            'model_providers.evolve_http.wire_api="responses"',
            'model_providers.evolve_http.env_http_headers={"api-key"="OPENAI_API_KEY"}',
            "model_providers.evolve_http.supports_websockets=false",
        ]
        parts = [super().build_cli_flags()]
        parts.extend(f"-c {shlex.quote(config)}" for config in configs)
        return " ".join(part for part in parts if part)
