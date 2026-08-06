from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class AuthenticationKind(StrEnum):
    API = "api"
    CODEX_AUTH_JSON = "codex_auth_json"


class AuthenticationErrorCode(StrEnum):
    CREDENTIAL_MISSING = "credential_missing"
    AUTH_JSON_MISSING = "auth_json_missing"
    AUTH_JSON_UNSUPPORTED = "auth_json_unsupported"


class RuntimeAuthenticationError(ValueError):
    def __init__(self, code: AuthenticationErrorCode, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ResolvedAuthentication:
    kind: AuthenticationKind
    values: tuple[tuple[str, str], ...]

    def environment(self) -> dict[str, str]:
        return dict(self.values)


_CODEX_AGENT_KINDS = frozenset({"codex", "target.agent:harboragent"})


def resolve_authentication(
    agent_kind: str,
    environment: Mapping[str, str],
) -> ResolvedAuthentication:
    codex_capable = agent_kind.strip().lower() in _CODEX_AGENT_KINDS
    configured_auth = environment.get("CODEX_AUTH_JSON_PATH")
    if configured_auth:
        if not codex_capable:
            raise RuntimeAuthenticationError(
                AuthenticationErrorCode.AUTH_JSON_UNSUPPORTED,
                "configured Codex auth.json is unsupported by the selected agent",
            )
        auth_path = Path(configured_auth).expanduser().resolve()
        if not auth_path.is_file():
            raise RuntimeAuthenticationError(
                AuthenticationErrorCode.AUTH_JSON_MISSING,
                "configured Codex auth.json does not exist or is not a regular file",
            )
        values = {"CODEX_AUTH_JSON_PATH": str(auth_path)}
        if base_url := environment.get("OPENAI_BASE_URL"):
            values["OPENAI_BASE_URL"] = _single_line("OPENAI_BASE_URL", base_url)
        return ResolvedAuthentication(
            AuthenticationKind.CODEX_AUTH_JSON,
            tuple(sorted(values.items())),
        )

    api_key = environment.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeAuthenticationError(
            AuthenticationErrorCode.CREDENTIAL_MISSING,
            "required API credential is missing: OPENAI_API_KEY",
        )
    values = {"OPENAI_API_KEY": _single_line("OPENAI_API_KEY", api_key)}
    if base_url := environment.get("OPENAI_BASE_URL"):
        values["OPENAI_BASE_URL"] = _single_line("OPENAI_BASE_URL", base_url)
    return ResolvedAuthentication(AuthenticationKind.API, tuple(sorted(values.items())))


def _single_line(name: str, value: str) -> str:
    if "\0" in value or "\n" in value or "\r" in value:
        raise RuntimeAuthenticationError(
            AuthenticationErrorCode.CREDENTIAL_MISSING,
            f"runtime authentication value for {name} must be single-line",
        )
    return value
