import json

import pytest

from evolve.runtime_config import (
    CandidateRuntimeConfig,
    ModelEndpointRoute,
    ProxyMode,
    ProxyRoutingConfig,
    RuntimeConfigError,
    load_resolved_runtime,
    model_endpoint_digest,
    normalize_model_endpoint,
    normalize_runtime_config,
    resolve_runtime,
)


def test_runtime_configuration_is_inline_and_minimal() -> None:
    assert normalize_runtime_config(None) is None
    assert normalize_runtime_config(
        {
            "candidate": {"variant": "uv", "project": "target", "python": "3.12"},
            "proxy": {"mode": "optional", "model_endpoint": "bypass"},
        }
    ) == {
        "candidate": {"variant": "uv", "project": "target", "python": "3.12"},
        "proxy": {"mode": "optional", "model_endpoint": "bypass"},
    }


def test_resolved_runtime_contains_only_safe_concrete_configuration() -> None:
    resolved = resolve_runtime(
        {
            "candidate": {"variant": "uv", "project": "target", "python": "3.12"},
            "proxy": {"mode": "required", "model_endpoint": "bypass"},
        },
        engine="harbor",
        environment={"OPENAI_BASE_URL": "https://MODEL.EXAMPLE/v1/"},
    )

    assert resolved.config.candidate == CandidateRuntimeConfig("uv", "target", "3.12")
    assert resolved.config.proxy == ProxyRoutingConfig(ProxyMode.REQUIRED, ModelEndpointRoute.BYPASS)
    assert resolved.endpoint_digest == model_endpoint_digest("https://model.example/v1")
    assert load_resolved_runtime(resolved.to_dict()) == resolved
    assert "model.example" not in json.dumps(resolved.to_dict())


@pytest.mark.parametrize(
    "runtime",
    [
        {"profile": "harbor-uv-v1"},
        {"candidate": {"variant": "pip", "project": "target", "python": "3.12"}},
        {"candidate": {"variant": "uv", "project": "../target", "python": "3.12"}},
        {"candidate": {"variant": "uv", "project": "target", "python": "three"}},
        {"proxy": {"mode": "sometimes", "model_endpoint": "bypass"}},
        {"proxy": {"mode": "optional", "model_endpoint": "proxy"}},
        {"proxy": {"mode": "optional", "model_endpoint": "bypass", "extra": True}},
    ],
)
def test_runtime_configuration_rejects_unknown_or_unsupported_values(
    runtime: dict[str, object],
) -> None:
    with pytest.raises(RuntimeConfigError):
        normalize_runtime_config(runtime)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://model.example/v1",
        "https://user@model.example/v1",
        "https://model.example/v1?region=test",
        "https:///v1",
    ],
)
def test_endpoint_normalization_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(RuntimeConfigError, match="OPENAI_BASE_URL"):
        normalize_model_endpoint(url)


def test_resolved_runtime_loader_rejects_tampering() -> None:
    payload = resolve_runtime(None, engine="harbor", environment={}).to_dict()
    payload["digest"] = "0" * 64
    with pytest.raises(RuntimeConfigError, match="digest"):
        load_resolved_runtime(payload)
