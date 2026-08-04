import json

import pytest

from evolve.runtime_profiles import (
    CandidateRuntimePolicy,
    RuntimeProfileResolutionError,
    load_resolved_runtime_profile,
    model_route_digest,
    normalize_model_route,
    resolve_runtime_profile,
    runtime_profile,
)


def strict_config(profile: str = "harbor-bytedance-v1") -> dict[str, object]:
    return {
        "experiment": {"id": "test"},
        "target": {"seed": "builtin-codex"},
        "surface": {"include": ["target/**"], "exclude": []},
        "operators": {"meta_agent": {"agent": "codex"}},
        "evaluator": {
            "engine": "harbor",
            "agent": "target.agent:HarborAgent",
            "runtime": {"profile": profile},
        },
    }


def test_strict_profiles_are_capability_based_and_versioned() -> None:
    basic = runtime_profile("harbor-bytedance-v1")
    uv = runtime_profile("harbor-bytedance-uv-v1")

    assert basic.schema_version == 1
    assert basic.candidate_runtime is None
    assert uv.candidate_runtime == CandidateRuntimePolicy("uv", "target", "3.12")
    assert basic.forbidden_credentials == ("CODEX_AUTH_JSON_PATH", "CODEX_FORCE_AUTH_JSON")
    assert basic.model_route == "bytedance-openai-compatible"
    assert basic.smoke_capabilities == ("one-model-request",)


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(RuntimeProfileResolutionError, match="unknown runtime profile"):
        runtime_profile("harbor-bytedance-v2")


def test_route_digest_normalizes_equivalent_urls_without_persisting_url() -> None:
    first = model_route_digest("https://MODEL.EXAMPLE/v1/")
    second = model_route_digest("https://model.example/v1")
    default_port = model_route_digest("https://model.example:443/v1")
    assert first == second == default_port

    resolved = resolve_runtime_profile(
        strict_config(),
        "sha256:runtime",
        {"OPENAI_BASE_URL": "https://model.example/v1"},
    )

    assert resolved is not None
    serialized = json.dumps(resolved.to_dict())
    assert "model.example" not in serialized
    assert resolved.model_route_digest == first
    assert load_resolved_runtime_profile(resolved.to_dict()) == resolved


@pytest.mark.parametrize(
    "url",
    [
        "ftp://model.example/v1",
        "https://user@model.example/v1",
        "https://user:password@model.example/v1",
        "https://model.example/v1?region=test",
        "https://model.example/v1#fragment",
        "https:///v1",
    ],
)
def test_route_normalization_rejects_ambiguous_or_unsafe_urls(url: str) -> None:
    with pytest.raises(RuntimeProfileResolutionError, match="OPENAI_BASE_URL"):
        normalize_model_route(url)


def test_legacy_config_resolves_no_profile() -> None:
    config = strict_config()
    evaluator = config["evaluator"]
    assert isinstance(evaluator, dict)
    evaluator.pop("runtime")

    assert resolve_runtime_profile(config, "sha256:runtime", {}) is None


@pytest.mark.parametrize(
    ("section", "name"),
    [
        ("evaluator", "OPENAI_API_KEY"),
        ("evaluator", "HTTPS_PROXY"),
        ("meta_agent", "OPENAI_BASE_URL"),
        ("meta_agent", "NO_PROXY"),
        ("meta_agent", "CODEX_AUTH_JSON_PATH"),
    ],
)
def test_strict_profile_rejects_runtime_policy_in_agent_env(section: str, name: str) -> None:
    config = strict_config()
    if section == "evaluator":
        evaluator = config["evaluator"]
        assert isinstance(evaluator, dict)
        evaluator["agent_env"] = {name: "configured-value"}
    else:
        operators = config["operators"]
        assert isinstance(operators, dict)
        meta_agent = operators["meta_agent"]
        assert isinstance(meta_agent, dict)
        meta_agent["agent_env"] = {name: "configured-value"}

    with pytest.raises(RuntimeProfileResolutionError, match=name):
        resolve_runtime_profile(
            config,
            "sha256:runtime",
            {"OPENAI_BASE_URL": "https://model.example/v1"},
        )


def test_resolved_profile_loader_rejects_tampered_digest() -> None:
    resolved = resolve_runtime_profile(
        strict_config(),
        "sha256:runtime",
        {"OPENAI_BASE_URL": "https://model.example/v1"},
    )
    assert resolved is not None
    payload = resolved.to_dict()
    payload["profile_digest"] = "0" * 64

    with pytest.raises(RuntimeProfileResolutionError, match="profile_digest"):
        load_resolved_runtime_profile(payload)


def test_resolved_profile_loader_rejects_unknown_empty_credential_role() -> None:
    resolved = resolve_runtime_profile(
        strict_config(),
        "sha256:runtime",
        {"OPENAI_BASE_URL": "https://model.example/v1"},
    )
    assert resolved is not None
    payload = resolved.to_dict()
    roles = payload["required_credentials_by_role"]
    assert isinstance(roles, dict)
    roles[""] = []

    with pytest.raises(RuntimeProfileResolutionError, match="credential role"):
        load_resolved_runtime_profile(payload)


def test_resolved_profile_loader_accepts_equivalent_role_mapping_order() -> None:
    resolved = resolve_runtime_profile(
        strict_config(),
        "sha256:runtime",
        {"OPENAI_BASE_URL": "https://model.example/v1"},
    )
    assert resolved is not None
    payload = resolved.to_dict()
    roles = payload["required_credentials_by_role"]
    assert isinstance(roles, dict)
    payload["required_credentials_by_role"] = dict(reversed(tuple(roles.items())))

    assert load_resolved_runtime_profile(payload) == resolved
