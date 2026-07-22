"""Harbor Codex adapter for an OpenAI-compatible Model Hub bridge."""

from __future__ import annotations

import json
import shlex

from harbor.agents.installed.codex import Codex


class ModelHubCodexAgent(Codex):
    """Configure Codex's isolated runtime for the official local bridge."""

    def _required_env(self, name: str) -> str:
        value = self._get_env(name)
        if not value:
            raise RuntimeError(f"{name} is required for ModelHubCodexAgent")
        return value

    def build_cli_flags(self) -> str:
        base_url = self._required_env("OPENAI_BASE_URL")
        self._required_env("OPENAI_API_KEY")

        settings = (
            'model_provider="my_model_hub"',
            'forced_login_method="api"',
            'model_providers.my_model_hub.name="My Model Hub"',
            f"model_providers.my_model_hub.base_url={json.dumps(base_url)}",
            'model_providers.my_model_hub.env_key="OPENAI_API_KEY"',
            'model_providers.my_model_hub.wire_api="responses"',
            "model_providers.my_model_hub.supports_websockets=false",
        )
        provider_flags = " ".join(f"-c {shlex.quote(value)}" for value in settings)
        inherited = super().build_cli_flags()
        return " ".join(part for part in (inherited, provider_flags) if part)
