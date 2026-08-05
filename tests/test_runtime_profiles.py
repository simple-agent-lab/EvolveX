import json
from importlib import resources
from pathlib import Path

import pytest

from evolve.runtime_profiles import (
    CandidateRuntimePolicy,
    RuntimeProfileResolutionError,
    load_resolved_runtime_profile,
    model_endpoint_digest,
    normalize_model_endpoint,
    profile_payload,
    resolve_runtime_profile,
    runtime_profile,
)


def strict_config(profile: str = "harbor-v1") -> dict[str, object]:
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
    basic = runtime_profile("harbor-v1", {})
    uv = runtime_profile("harbor-uv-v1", {})

    assert basic.schema_version == 1
    assert basic.candidate_runtime is None
    assert uv.candidate_runtime == CandidateRuntimePolicy("uv", "target", "3.12")
    assert basic.smoke_capabilities == ("one-model-request",)
    assert "bytedance" not in json.dumps(profile_payload(basic)).lower()


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(RuntimeProfileResolutionError, match="unknown runtime profile"):
        runtime_profile("harbor-v2", {})


def test_endpoint_digest_normalizes_equivalent_urls_without_persisting_url() -> None:
    first = model_endpoint_digest("https://MODEL.EXAMPLE/v1/")
    second = model_endpoint_digest("https://model.example/v1")
    default_port = model_endpoint_digest("https://model.example:443/v1")
    assert first == second == default_port

    resolved = resolve_runtime_profile(
        strict_config(),
        "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        {"OPENAI_BASE_URL": "https://model.example/v1"},
    )

    assert resolved is not None
    serialized = json.dumps(resolved.to_dict())
    assert "model.example" not in serialized
    assert resolved.endpoint_digest == first
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
def test_endpoint_normalization_rejects_ambiguous_or_unsafe_urls(url: str) -> None:
    with pytest.raises(RuntimeProfileResolutionError, match="OPENAI_BASE_URL"):
        normalize_model_endpoint(url)


def test_official_endpoint_is_used_when_base_url_is_unset() -> None:
    resolved = resolve_runtime_profile(
        strict_config(),
        "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        {},
    )
    assert resolved is not None
    assert resolved.endpoint_digest == model_endpoint_digest(None)


def test_private_profile_directory_is_loaded_by_name(tmp_path: Path) -> None:
    (tmp_path / "private.yaml").write_text(
        "schema_version: 1\n"
        "name: private-harbor-v1\n"
        "engine: harbor\n"
        "required_tools: [docker, harbor]\n"
        "candidate_runtime: null\n"
        "dependency_policy: agent-owned\n"
        "cache_policy: none\n"
        "network_policy: model-endpoint\n"
        "preflight_capabilities: [configuration, evaluation-contract, runtime-image]\n"
        "smoke_capabilities: [one-model-request]\n"
    )
    profile = runtime_profile(
        "private-harbor-v1", {"EVOLVE_RUNTIME_PROFILE_PATH": str(tmp_path)}
    )
    assert profile.name == "private-harbor-v1"


def test_duplicate_profile_name_is_rejected(tmp_path: Path) -> None:
    built_in = resources.files("evolve").joinpath("profiles/harbor-v1.yaml").read_text()
    (tmp_path / "duplicate.yaml").write_text(built_in)
    with pytest.raises(RuntimeProfileResolutionError, match="multiple runtime profiles"):
        runtime_profile("harbor-v1", {"EVOLVE_RUNTIME_PROFILE_PATH": str(tmp_path)})


@pytest.mark.parametrize("runtime", ["ubuntu:latest", "sha256:short", "image @sha256:" + "a" * 64])
def test_strict_profile_requires_immutable_runtime_reference(runtime: str) -> None:
    with pytest.raises(RuntimeProfileResolutionError, match="immutable SHA-256"):
        resolve_runtime_profile(strict_config(), runtime, {})


def test_legacy_config_resolves_no_profile() -> None:
    config = strict_config()
    evaluator = config["evaluator"]
    assert isinstance(evaluator, dict)
    evaluator.pop("runtime")

    assert resolve_runtime_profile(config, "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", {}) is None


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
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            {"OPENAI_BASE_URL": "https://model.example/v1"},
        )


def test_resolved_profile_loader_rejects_tampered_digest() -> None:
    resolved = resolve_runtime_profile(
        strict_config(),
        "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        {"OPENAI_BASE_URL": "https://model.example/v1"},
    )
    assert resolved is not None
    payload = resolved.to_dict()
    payload["profile_digest"] = "0" * 64

    with pytest.raises(RuntimeProfileResolutionError, match="profile_digest"):
        load_resolved_runtime_profile(payload)


def test_resolved_profile_loader_rejects_unknown_profile_field() -> None:
    resolved = resolve_runtime_profile(
        strict_config(),
        "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        {"OPENAI_BASE_URL": "https://model.example/v1"},
    )
    assert resolved is not None
    payload = resolved.to_dict()
    payload["private_route"] = "not-allowed"

    with pytest.raises(RuntimeProfileResolutionError, match="unknown resolved runtime profile fields"):
        load_resolved_runtime_profile(payload)
