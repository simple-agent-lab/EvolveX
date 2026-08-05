from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit, urlunsplit

import yaml


class RuntimeProfileErrorCode(StrEnum):
    PROFILE_NOT_FOUND = "profile_not_found"
    PROFILE_AMBIGUOUS = "profile_ambiguous"
    PROFILE_INVALID = "profile_invalid"
    ENDPOINT_INVALID = "endpoint_invalid"
    RUNTIME_IMAGE_MUTABLE = "runtime_image_mutable"


class RuntimeProfileResolutionError(ValueError):
    def __init__(self, message: str, *, code: RuntimeProfileErrorCode = RuntimeProfileErrorCode.PROFILE_INVALID):
        self.code = code
        super().__init__(message)


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
    required_tools: tuple[str, ...]
    candidate_runtime: CandidateRuntimePolicy | None
    dependency_policy: str
    cache_policy: str
    network_policy: str
    preflight_capabilities: tuple[str, ...]
    smoke_capabilities: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedRuntimeProfileV1:
    profile: RuntimeProfileV1
    runtime_digest: str
    endpoint_digest: str
    profile_digest: str

    def to_dict(self) -> dict[str, object]:
        return resolved_runtime_profile_payload(self)


_PROFILE_FIELDS = {
    "schema_version",
    "name",
    "engine",
    "required_tools",
    "candidate_runtime",
    "dependency_policy",
    "cache_policy",
    "network_policy",
    "preflight_capabilities",
    "smoke_capabilities",
}
_RESOLVED_FIELDS = _PROFILE_FIELDS | {"runtime_digest", "endpoint_digest", "profile_digest"}
_PROTECTED_ENVIRONMENT_NAMES = {
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "CODEX_AUTH_JSON_PATH",
    "CODEX_FORCE_AUTH_JSON",
}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_IMMUTABLE_IMAGE = re.compile(r"(?:[^\s@]+@)?sha256:[0-9a-f]{64}")
_OFFICIAL_OPENAI_ENDPOINT = "https://api.openai.com/v1"
_BUILTIN_PROFILE_DIRECTORY = Path(__file__).resolve().parent / "profiles"


def profile_search_paths(environment: Mapping[str, str]) -> tuple[Path, ...]:
    configured = environment.get("EVOLVE_RUNTIME_PROFILE_PATH", "")
    private = tuple(Path(entry).expanduser().resolve() for entry in configured.split(os.pathsep) if entry.strip())
    return (*private, _BUILTIN_PROFILE_DIRECTORY)


def runtime_profile(
    name: str, environment: Mapping[str, str] | None = None
) -> RuntimeProfileV1:
    requested = name.strip()
    if not requested:
        raise RuntimeProfileResolutionError("runtime profile name must be non-empty")
    matches: list[RuntimeProfileV1] = []
    for directory in profile_search_paths(environment or {}):
        if not directory.is_dir():
            continue
        for path in sorted((*directory.glob("*.yaml"), *directory.glob("*.yml"), *directory.glob("*.json"))):
            profile = _load_profile_file(path)
            if profile.name == requested:
                matches.append(profile)
    if not matches:
        raise RuntimeProfileResolutionError(
            f"unknown runtime profile: {requested}",
            code=RuntimeProfileErrorCode.PROFILE_NOT_FOUND,
        )
    if len(matches) != 1:
        raise RuntimeProfileResolutionError(
            f"multiple runtime profiles resolve name: {requested}",
            code=RuntimeProfileErrorCode.PROFILE_AMBIGUOUS,
        )
    return matches[0]


def normalize_model_endpoint(url: str | None) -> str:
    value = _OFFICIAL_OPENAI_ENDPOINT if url is None or not url.strip() else url.strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise RuntimeProfileResolutionError(
            "OPENAI_BASE_URL is invalid", code=RuntimeProfileErrorCode.ENDPOINT_INVALID
        ) from error
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise RuntimeProfileResolutionError(
            "OPENAI_BASE_URL must use HTTP or HTTPS", code=RuntimeProfileErrorCode.ENDPOINT_INVALID
        )
    if parsed.username is not None or parsed.password is not None:
        raise RuntimeProfileResolutionError(
            "OPENAI_BASE_URL must not contain user information",
            code=RuntimeProfileErrorCode.ENDPOINT_INVALID,
        )
    if parsed.query or parsed.fragment:
        raise RuntimeProfileResolutionError(
            "OPENAI_BASE_URL must not contain a query or fragment",
            code=RuntimeProfileErrorCode.ENDPOINT_INVALID,
        )
    hostname = parsed.hostname
    if not hostname:
        raise RuntimeProfileResolutionError(
            "OPENAI_BASE_URL must contain a hostname", code=RuntimeProfileErrorCode.ENDPOINT_INVALID
        )
    normalized_host = hostname.lower()
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    if (scheme, port) in {("http", 80), ("https", 443)}:
        port = None
    netloc = f"{normalized_host}:{port}" if port is not None else normalized_host
    return urlunsplit((scheme, netloc, parsed.path.rstrip("/"), "", ""))


def model_endpoint_digest(url: str | None) -> str:
    return hashlib.sha256(normalize_model_endpoint(url).encode()).hexdigest()


def normalize_model_route(url: str) -> str:
    return normalize_model_endpoint(url)


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
    profile = runtime_profile(name, environment)
    engine = evaluator.get("engine")
    if engine != profile.engine:
        raise RuntimeProfileResolutionError(
            f"runtime profile {profile.name} requires evaluator.engine {profile.engine}"
        )
    resolved_runtime = _immutable_runtime_digest(runtime_digest)
    _reject_protected_overrides(config, evaluator)
    endpoint_digest = model_endpoint_digest(environment.get("OPENAI_BASE_URL"))
    resolved_digest = _resolved_digest(profile, resolved_runtime, endpoint_digest)
    return ResolvedRuntimeProfileV1(profile, resolved_runtime, endpoint_digest, resolved_digest)


def profile_payload(profile: RuntimeProfileV1) -> dict[str, object]:
    candidate = profile.candidate_runtime
    return {
        "schema_version": profile.schema_version,
        "name": profile.name,
        "engine": profile.engine,
        "required_tools": list(profile.required_tools),
        "candidate_runtime": (
            None
            if candidate is None
            else {"variant": candidate.variant, "project": candidate.project, "python": candidate.python}
        ),
        "dependency_policy": profile.dependency_policy,
        "cache_policy": profile.cache_policy,
        "network_policy": profile.network_policy,
        "preflight_capabilities": list(profile.preflight_capabilities),
        "smoke_capabilities": list(profile.smoke_capabilities),
    }


def resolved_runtime_profile_payload(profile: ResolvedRuntimeProfileV1) -> dict[str, object]:
    return {
        **profile_payload(profile.profile),
        "runtime_digest": profile.runtime_digest,
        "endpoint_digest": profile.endpoint_digest,
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
    parsed = _parse_profile({field: raw[field] for field in _PROFILE_FIELDS})
    runtime_digest = _immutable_runtime_digest(_required_string(raw, "runtime_digest"))
    endpoint_digest = _required_sha256(raw, "endpoint_digest")
    profile_digest = _required_sha256(raw, "profile_digest")
    expected = _resolved_digest(parsed, runtime_digest, endpoint_digest)
    if profile_digest != expected:
        raise RuntimeProfileResolutionError("resolved runtime profile profile_digest does not match payload")
    return ResolvedRuntimeProfileV1(parsed, runtime_digest, endpoint_digest, profile_digest)


def _load_profile_file(path: Path) -> RuntimeProfileV1:
    try:
        payload = json.loads(path.read_text()) if path.suffix == ".json" else yaml.safe_load(path.read_text())
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise RuntimeProfileResolutionError(f"invalid runtime profile file: {path}") from error
    return _parse_profile(payload)


def _parse_profile(payload: object) -> RuntimeProfileV1:
    raw = _mapping(payload, "runtime profile")
    unknown = sorted(str(key) for key in raw if key not in _PROFILE_FIELDS)
    missing = sorted(_PROFILE_FIELDS - set(raw))
    if unknown or missing:
        details = []
        if unknown:
            details.append("unknown fields: " + ", ".join(unknown))
        if missing:
            details.append("missing fields: " + ", ".join(missing))
        raise RuntimeProfileResolutionError("invalid runtime profile schema: " + "; ".join(details))
    return RuntimeProfileV1(
        schema_version=_required_integer(raw, "schema_version"),
        name=_required_string(raw, "name"),
        engine=_required_string(raw, "engine"),
        required_tools=_string_tuple(raw.get("required_tools"), "required_tools"),
        candidate_runtime=_candidate_runtime(raw.get("candidate_runtime")),
        dependency_policy=_required_string(raw, "dependency_policy"),
        cache_policy=_required_string(raw, "cache_policy"),
        network_policy=_required_string(raw, "network_policy"),
        preflight_capabilities=_string_tuple(raw.get("preflight_capabilities"), "preflight_capabilities"),
        smoke_capabilities=_string_tuple(raw.get("smoke_capabilities"), "smoke_capabilities"),
    )


def _immutable_runtime_digest(value: str) -> str:
    normalized = value.strip().lower()
    if _IMMUTABLE_IMAGE.fullmatch(normalized) is None:
        raise RuntimeProfileResolutionError(
            "EVOLVE_RUNTIME_DIGEST must be an immutable SHA-256 image reference",
            code=RuntimeProfileErrorCode.RUNTIME_IMAGE_MUTABLE,
        )
    return normalized


def _resolved_digest(profile: RuntimeProfileV1, runtime_digest: str, endpoint_digest: str) -> str:
    return _canonical_digest(
        {
            "profile": profile_payload(profile),
            "runtime_digest": runtime_digest,
            "endpoint_digest": endpoint_digest,
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
            if is_protected_runtime_environment_name(name):
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
        raise RuntimeProfileResolutionError(f"runtime profile {field} must be a non-empty string")
    return value


def _required_integer(payload: Mapping[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeProfileResolutionError(f"runtime profile {field} must be an integer")
    return value


def _required_sha256(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RuntimeProfileResolutionError(f"resolved runtime profile {field} must be a SHA-256 digest")
    return value


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise RuntimeProfileResolutionError(f"runtime profile {field} must be a string list")
    return cast("tuple[str, ...]", tuple(value))


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
