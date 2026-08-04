from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlsplit, urlunsplit


class RuntimeProfileResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class CandidateRuntimePolicy:
    variant: str
    project: str
    python: str


@dataclass(frozen=True)
class RuntimeProfileV1:
    schema_version: int
    name: str
    engine: str
    model_route: str
    required_credentials_by_role: tuple[tuple[str, tuple[str, ...]], ...]
    forbidden_credentials: tuple[str, ...]
    required_tools: tuple[str, ...]
    candidate_runtime: CandidateRuntimePolicy | None
    dependency_policy: str
    cache_policy: str
    network_policy: str
    proxy_policy: str
    model_bypass_policy: str
    preflight_capabilities: tuple[str, ...]
    smoke_capabilities: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedRuntimeProfileV1:
    profile: RuntimeProfileV1
    runtime_digest: str
    model_route_digest: str
    profile_digest: str

    def to_dict(self) -> dict[str, object]:
        return resolved_runtime_profile_payload(self)


_REQUIRED_CREDENTIALS = (
    ("agent", ("OPENAI_API_KEY", "OPENAI_BASE_URL")),
    ("meta_agent", ("OPENAI_API_KEY", "OPENAI_BASE_URL")),
)
_FORBIDDEN_CREDENTIALS = ("CODEX_AUTH_JSON_PATH", "CODEX_FORCE_AUTH_JSON")
_COMMON_PROFILE = {
    "schema_version": 1,
    "engine": "harbor",
    "model_route": "bytedance-openai-compatible",
    "required_credentials_by_role": _REQUIRED_CREDENTIALS,
    "forbidden_credentials": _FORBIDDEN_CREDENTIALS,
    "proxy_policy": "dependency-proxy-model-bypass",
    "model_bypass_policy": "configured-model-host",
    "smoke_capabilities": ("one-model-request",),
}

_PROFILES = {
    "harbor-bytedance-v1": RuntimeProfileV1(
        name="harbor-bytedance-v1",
        required_tools=("docker", "harbor"),
        candidate_runtime=None,
        dependency_policy="agent-owned",
        cache_policy="none",
        network_policy="model-endpoint",
        preflight_capabilities=(
            "configuration",
            "evaluation-contract",
            "runtime-image",
            "credentials",
            "endpoint",
        ),
        **_COMMON_PROFILE,
    ),
    "harbor-bytedance-uv-v1": RuntimeProfileV1(
        name="harbor-bytedance-uv-v1",
        required_tools=("docker", "harbor", "uv"),
        candidate_runtime=CandidateRuntimePolicy("uv", "target", "3.12"),
        dependency_policy="uv-frozen",
        cache_policy="content-addressed-shared",
        network_policy="prepare-online-trial-offline",
        preflight_capabilities=(
            "configuration",
            "evaluation-contract",
            "runtime-image",
            "dependency-lock",
            "credentials",
            "endpoint",
        ),
        **_COMMON_PROFILE,
    ),
}

_PROFILE_FIELDS = {
    "schema_version",
    "name",
    "engine",
    "model_route",
    "required_credentials_by_role",
    "forbidden_credentials",
    "required_tools",
    "candidate_runtime",
    "dependency_policy",
    "cache_policy",
    "network_policy",
    "proxy_policy",
    "model_bypass_policy",
    "preflight_capabilities",
    "smoke_capabilities",
}
_RESOLVED_FIELDS = _PROFILE_FIELDS | {"runtime_digest", "model_route_digest", "profile_digest"}
_PROTECTED_ENVIRONMENT_NAMES = {
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    *_FORBIDDEN_CREDENTIALS,
}
_SHA256 = re.compile(r"[0-9a-f]{64}")


def runtime_profile(name: str) -> RuntimeProfileV1:
    try:
        return _PROFILES[name]
    except KeyError as error:
        raise RuntimeProfileResolutionError(f"unknown runtime profile: {name}") from error


def normalize_model_route(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise RuntimeProfileResolutionError("OPENAI_BASE_URL must be a non-empty HTTP or HTTPS URL")
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError as error:
        raise RuntimeProfileResolutionError("OPENAI_BASE_URL is invalid") from error
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise RuntimeProfileResolutionError("OPENAI_BASE_URL must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise RuntimeProfileResolutionError("OPENAI_BASE_URL must not contain user information")
    if parsed.query or parsed.fragment:
        raise RuntimeProfileResolutionError("OPENAI_BASE_URL must not contain a query or fragment")
    hostname = parsed.hostname
    if not hostname:
        raise RuntimeProfileResolutionError("OPENAI_BASE_URL must contain a hostname")
    normalized_host = hostname.lower()
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    netloc = f"{normalized_host}:{port}" if port is not None else normalized_host
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def model_route_digest(url: str) -> str:
    return hashlib.sha256(normalize_model_route(url).encode()).hexdigest()


def is_protected_runtime_environment_name(name: str) -> bool:
    return name.upper() in _PROTECTED_ENVIRONMENT_NAMES


def resolve_runtime_profile(
    config: Mapping[str, object],
    runtime_digest: str,
    environment: Mapping[str, str],
) -> ResolvedRuntimeProfileV1 | None:
    evaluator = _mapping(config.get("evaluator"), "evaluator")
    runtime = evaluator.get("runtime")
    if runtime is None:
        return None
    runtime_mapping = _mapping(runtime, "evaluator.runtime")
    unknown_runtime_fields = sorted(str(key) for key in runtime_mapping if key != "profile")
    if unknown_runtime_fields:
        raise RuntimeProfileResolutionError(
            "unknown evaluator.runtime fields: " + ", ".join(unknown_runtime_fields)
        )
    name = runtime_mapping.get("profile")
    if not isinstance(name, str) or not name.strip():
        raise RuntimeProfileResolutionError("evaluator.runtime.profile must be a non-empty string")
    if "candidate_runtime" in evaluator:
        raise RuntimeProfileResolutionError(
            "cannot combine evaluator.runtime.profile with evaluator.candidate_runtime"
        )
    profile = runtime_profile(name.strip())
    engine = evaluator.get("engine")
    if engine != profile.engine:
        raise RuntimeProfileResolutionError(
            f"runtime profile {profile.name} requires evaluator.engine {profile.engine}"
        )
    if not isinstance(runtime_digest, str) or not runtime_digest.strip():
        raise RuntimeProfileResolutionError("EVOLVE_RUNTIME_DIGEST must be non-empty")
    _reject_protected_overrides(config, evaluator)
    route = environment.get("OPENAI_BASE_URL", "")
    route_digest = model_route_digest(route)
    resolved_digest = _resolved_digest(profile, runtime_digest.strip(), route_digest)
    return ResolvedRuntimeProfileV1(profile, runtime_digest.strip(), route_digest, resolved_digest)


def resolved_runtime_profile_payload(profile: ResolvedRuntimeProfileV1) -> dict[str, object]:
    return {
        **_runtime_profile_payload(profile.profile),
        "runtime_digest": profile.runtime_digest,
        "model_route_digest": profile.model_route_digest,
        "profile_digest": profile.profile_digest,
    }


def load_resolved_runtime_profile(payload: object) -> ResolvedRuntimeProfileV1:
    raw = _mapping(payload, "resolved runtime profile")
    unknown = sorted(str(key) for key in raw if key not in _RESOLVED_FIELDS)
    missing = sorted(_RESOLVED_FIELDS - set(raw))
    if unknown:
        raise RuntimeProfileResolutionError("unknown resolved runtime profile fields: " + ", ".join(unknown))
    if missing:
        raise RuntimeProfileResolutionError("missing resolved runtime profile fields: " + ", ".join(missing))
    name = _required_string(raw, "name")
    registered = runtime_profile(name)
    parsed = RuntimeProfileV1(
        schema_version=_required_integer(raw, "schema_version"),
        name=name,
        engine=_required_string(raw, "engine"),
        model_route=_required_string(raw, "model_route"),
        required_credentials_by_role=_credential_roles(raw.get("required_credentials_by_role")),
        forbidden_credentials=_string_tuple(raw.get("forbidden_credentials"), "forbidden_credentials"),
        required_tools=_string_tuple(raw.get("required_tools"), "required_tools"),
        candidate_runtime=_candidate_runtime(raw.get("candidate_runtime")),
        dependency_policy=_required_string(raw, "dependency_policy"),
        cache_policy=_required_string(raw, "cache_policy"),
        network_policy=_required_string(raw, "network_policy"),
        proxy_policy=_required_string(raw, "proxy_policy"),
        model_bypass_policy=_required_string(raw, "model_bypass_policy"),
        preflight_capabilities=_string_tuple(raw.get("preflight_capabilities"), "preflight_capabilities"),
        smoke_capabilities=_string_tuple(raw.get("smoke_capabilities"), "smoke_capabilities"),
    )
    if parsed != registered:
        raise RuntimeProfileResolutionError(f"resolved runtime profile policy does not match registry: {name}")
    runtime_digest = _required_string(raw, "runtime_digest")
    route_digest = _required_sha256(raw, "model_route_digest")
    profile_digest = _required_sha256(raw, "profile_digest")
    expected = _resolved_digest(parsed, runtime_digest, route_digest)
    if profile_digest != expected:
        raise RuntimeProfileResolutionError("resolved runtime profile profile_digest does not match payload")
    return ResolvedRuntimeProfileV1(parsed, runtime_digest, route_digest, profile_digest)


def _runtime_profile_payload(profile: RuntimeProfileV1) -> dict[str, object]:
    candidate = profile.candidate_runtime
    return {
        "schema_version": profile.schema_version,
        "name": profile.name,
        "engine": profile.engine,
        "model_route": profile.model_route,
        "required_credentials_by_role": {
            role: list(names) for role, names in profile.required_credentials_by_role
        },
        "forbidden_credentials": list(profile.forbidden_credentials),
        "required_tools": list(profile.required_tools),
        "candidate_runtime": (
            None
            if candidate is None
            else {"variant": candidate.variant, "project": candidate.project, "python": candidate.python}
        ),
        "dependency_policy": profile.dependency_policy,
        "cache_policy": profile.cache_policy,
        "network_policy": profile.network_policy,
        "proxy_policy": profile.proxy_policy,
        "model_bypass_policy": profile.model_bypass_policy,
        "preflight_capabilities": list(profile.preflight_capabilities),
        "smoke_capabilities": list(profile.smoke_capabilities),
    }


def _resolved_digest(profile: RuntimeProfileV1, runtime_digest: str, route_digest: str) -> str:
    return _canonical_digest(
        {
            "profile": _runtime_profile_payload(profile),
            "runtime_digest": runtime_digest,
            "model_route_digest": route_digest,
        }
    )


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _reject_protected_overrides(
    config: Mapping[str, object], evaluator: Mapping[str, object]
) -> None:
    override_blocks: list[tuple[str, object]] = [
        ("evaluator.agent_env", evaluator.get("agent_env")),
        ("evaluator.verifier_env", evaluator.get("verifier_env")),
    ]
    operators = config.get("operators")
    if isinstance(operators, Mapping):
        meta_agent = operators.get("meta_agent")
        if isinstance(meta_agent, Mapping):
            override_blocks.append(("operators.meta_agent.agent_env", meta_agent.get("agent_env")))
    for field, value in override_blocks:
        if value is None:
            continue
        values = _mapping(value, field)
        for name in values:
            if isinstance(name, str) and is_protected_runtime_environment_name(name):
                raise RuntimeProfileResolutionError(f"{field} must not configure protected name {name}")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RuntimeProfileResolutionError(f"{field} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise RuntimeProfileResolutionError(f"{field} keys must be strings")
    return cast("Mapping[str, object]", value)


def _required_string(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise RuntimeProfileResolutionError(f"resolved runtime profile {field} must be a non-empty string")
    return value


def _required_integer(payload: Mapping[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeProfileResolutionError(f"resolved runtime profile {field} must be an integer")
    return value


def _required_sha256(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RuntimeProfileResolutionError(f"resolved runtime profile {field} must be a SHA-256 digest")
    return value


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise RuntimeProfileResolutionError(f"resolved runtime profile {field} must be a string list")
    return cast("tuple[str, ...]", tuple(value))


def _credential_roles(value: object) -> tuple[tuple[str, tuple[str, ...]], ...]:
    roles = _mapping(value, "required_credentials_by_role")
    return tuple(
        (role, _string_tuple(names, f"required_credentials_by_role.{role}"))
        for role, names in roles.items()
        if isinstance(role, str) and role
    )


def _candidate_runtime(value: object) -> CandidateRuntimePolicy | None:
    if value is None:
        return None
    raw = _mapping(value, "candidate_runtime")
    if set(raw) != {"variant", "project", "python"}:
        raise RuntimeProfileResolutionError("resolved candidate_runtime fields are invalid")
    return CandidateRuntimePolicy(
        _required_string(raw, "variant"),
        _required_string(raw, "project"),
        _required_string(raw, "python"),
    )
