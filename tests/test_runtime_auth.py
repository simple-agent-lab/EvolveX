from pathlib import Path

import pytest

from evolve.runtime_auth import (
    AuthenticationErrorCode,
    AuthenticationKind,
    RuntimeAuthenticationError,
    resolve_authentication,
)


def test_codex_prefers_explicit_auth_json(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text('{"tokens": {}}\n')

    result = resolve_authentication(
        "codex",
        {"CODEX_AUTH_JSON_PATH": str(auth), "OPENAI_API_KEY": "api-key"},
    )

    assert result.kind is AuthenticationKind.CODEX_AUTH_JSON
    assert result.environment() == {"CODEX_AUTH_JSON_PATH": str(auth.resolve())}


def test_codex_defaults_to_api_without_base_url() -> None:
    result = resolve_authentication("codex", {"OPENAI_API_KEY": "api-key"})

    assert result.kind is AuthenticationKind.API
    assert result.environment() == {"OPENAI_API_KEY": "api-key"}


def test_api_auth_includes_optional_base_url() -> None:
    result = resolve_authentication(
        "codex",
        {"OPENAI_API_KEY": "api-key", "OPENAI_BASE_URL": "https://model.example/v1"},
    )

    assert result.environment() == {
        "OPENAI_API_KEY": "api-key",
        "OPENAI_BASE_URL": "https://model.example/v1",
    }


def test_codex_does_not_discover_home_auth_json(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    auth = home / ".codex" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text("{}\n")
    monkeypatch.setenv("HOME", str(home))

    with pytest.raises(RuntimeAuthenticationError) as excinfo:
        resolve_authentication("codex", {})

    assert excinfo.value.code is AuthenticationErrorCode.CREDENTIAL_MISSING


def test_missing_explicit_auth_json_is_typed_without_exposing_path(tmp_path: Path) -> None:
    missing = tmp_path / "private" / "auth.json"

    with pytest.raises(RuntimeAuthenticationError) as excinfo:
        resolve_authentication("codex", {"CODEX_AUTH_JSON_PATH": str(missing)})

    assert excinfo.value.code is AuthenticationErrorCode.AUTH_JSON_MISSING
    assert str(missing) not in str(excinfo.value)


def test_non_codex_rejects_auth_json(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n")

    with pytest.raises(RuntimeAuthenticationError) as excinfo:
        resolve_authentication("mini-swe-agent", {"CODEX_AUTH_JSON_PATH": str(auth)})

    assert excinfo.value.code is AuthenticationErrorCode.AUTH_JSON_UNSUPPORTED


def test_unknown_agent_requires_api_credentials() -> None:
    with pytest.raises(RuntimeAuthenticationError) as excinfo:
        resolve_authentication("custom.agent:Agent", {})

    assert excinfo.value.code is AuthenticationErrorCode.CREDENTIAL_MISSING


def test_shipped_harbor_agent_supports_explicit_auth_json(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n")

    result = resolve_authentication(
        "target.agent:HarborAgent", {"CODEX_AUTH_JSON_PATH": str(auth)}
    )

    assert result.kind is AuthenticationKind.CODEX_AUTH_JSON
