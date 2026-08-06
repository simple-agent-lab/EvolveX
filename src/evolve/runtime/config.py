from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import cast
from urllib.parse import urlsplit, urlunsplit


class RuntimeConfigError(ValueError):
    pass


class ProxyMode(StrEnum):
    OPTIONAL = "optional"
    REQUIRED = "required"


class ModelEndpointRoute(StrEnum):
    BYPASS = "bypass"


@dataclass(frozen=True)
class CandidateRuntimeConfig:
    variant: str
    project: str
    python: str

    def to_dict(self) -> dict[str, str]:
        return {
            "variant": self.variant,
            "project": self.project,
            "python": self.python,
        }


@dataclass(frozen=True)
class ProxyRoutingConfig:
    mode: ProxyMode
    model_endpoint: ModelEndpointRoute

    def to_dict(self) -> dict[str, str]:
        return {"mode": self.mode.value, "model_endpoint": self.model_endpoint.value}


@dataclass(frozen=True)
class RuntimeConfigV1:
    candidate: CandidateRuntimeConfig | None = None
    proxy: ProxyRoutingConfig | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.candidate is not None:
            payload["candidate"] = self.candidate.to_dict()
        if self.proxy is not None:
            payload["proxy"] = self.proxy.to_dict()
        return payload


@dataclass(frozen=True)
class ResolvedRuntimeV1:
    config: RuntimeConfigV1
    engine: str
    endpoint_digest: str
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "engine": self.engine,
            **self.config.to_dict(),
            "endpoint_digest": self.endpoint_digest,
            "digest": self.digest,
        }


_RUNTIME_FIELDS = {"candidate", "proxy"}
_RESOLVED_FIELDS = {
    "schema_version",
    "engine",
    "candidate",
    "proxy",
    "endpoint_digest",
    "digest",
}
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
_PYTHON_VERSION = re.compile(r"[0-9]+\.[0-9]+")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_OFFICIAL_OPENAI_ENDPOINT = "https://api.openai.com/v1"


def normalize_runtime_config(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    return _parse_runtime(value).to_dict()


def parse_runtime_config(value: object) -> RuntimeConfigV1:
    return RuntimeConfigV1() if value is None else _parse_runtime(value)


def resolve_runtime(
    value: object,
    *,
    engine: object,
    environment: Mapping[str, str],
) -> ResolvedRuntimeV1:
    if not isinstance(engine, str) or not engine:
        raise RuntimeConfigError("evaluator.engine must be a non-empty string")
    config = parse_runtime_config(value)
    endpoint = model_endpoint_digest(environment.get("OPENAI_BASE_URL"))
    payload = {
        "schema_version": 1,
        "engine": engine,
        **config.to_dict(),
        "endpoint_digest": endpoint,
    }
    return ResolvedRuntimeV1(config, engine, endpoint, _canonical_digest(payload))


def load_resolved_runtime(payload: object) -> ResolvedRuntimeV1:
    raw = _mapping(payload, "resolved runtime")
    unknown = sorted(set(raw) - _RESOLVED_FIELDS)
    required = {"schema_version", "engine", "endpoint_digest", "digest"}
    missing = sorted(required - set(raw))
    if unknown or missing:
        details = []
        if unknown:
            details.append("unknown fields: " + ", ".join(unknown))
        if missing:
            details.append("missing fields: " + ", ".join(missing))
        raise RuntimeConfigError("invalid resolved runtime schema: " + "; ".join(details))
    if raw["schema_version"] != 1:
        raise RuntimeConfigError("resolved runtime schema_version must be 1")
    config = _parse_runtime({key: raw[key] for key in _RUNTIME_FIELDS if key in raw})
    engine = _string(raw, "engine", "resolved runtime")
    endpoint = _sha256(raw, "endpoint_digest")
    digest = _sha256(raw, "digest")
    expected = _canonical_digest(
        {
            "schema_version": 1,
            "engine": engine,
            **config.to_dict(),
            "endpoint_digest": endpoint,
        }
    )
    if digest != expected:
        raise RuntimeConfigError("resolved runtime digest does not match payload")
    return ResolvedRuntimeV1(config, engine, endpoint, digest)


def normalize_model_endpoint(url: str | None) -> str:
    value = _OFFICIAL_OPENAI_ENDPOINT if url is None or not url.strip() else url.strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise RuntimeConfigError("OPENAI_BASE_URL is invalid") from error
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise RuntimeConfigError("OPENAI_BASE_URL must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise RuntimeConfigError("OPENAI_BASE_URL must not contain user information")
    if parsed.query or parsed.fragment:
        raise RuntimeConfigError("OPENAI_BASE_URL must not contain a query or fragment")
    hostname = parsed.hostname
    if not hostname:
        raise RuntimeConfigError("OPENAI_BASE_URL must contain a hostname")
    normalized_host = hostname.lower()
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    if (scheme, port) in {("http", 80), ("https", 443)}:
        port = None
    netloc = f"{normalized_host}:{port}" if port is not None else normalized_host
    return urlunsplit((scheme, netloc, parsed.path.rstrip("/"), "", ""))


def model_endpoint_digest(url: str | None) -> str:
    return hashlib.sha256(normalize_model_endpoint(url).encode()).hexdigest()


def model_endpoint_hostname(url: str | None) -> str:
    hostname = urlsplit(normalize_model_endpoint(url)).hostname
    assert hostname is not None
    return hostname.lower()


def is_protected_runtime_environment_name(name: str) -> bool:
    return name.upper() in _PROTECTED_ENVIRONMENT_NAMES


def _parse_runtime(value: object) -> RuntimeConfigV1:
    raw = _mapping(value, "evaluator.runtime")
    unknown = sorted(set(raw) - _RUNTIME_FIELDS)
    if unknown:
        raise RuntimeConfigError("unknown evaluator.runtime fields: " + ", ".join(unknown))
    return RuntimeConfigV1(
        candidate=_candidate(raw.get("candidate")),
        proxy=_proxy(raw.get("proxy")),
    )


def _candidate(value: object) -> CandidateRuntimeConfig | None:
    if value is None:
        return None
    raw = _mapping(value, "evaluator.runtime.candidate")
    if set(raw) != {"variant", "project", "python"}:
        raise RuntimeConfigError("evaluator.runtime.candidate fields must be variant, project, and python")
    variant = _string(raw, "variant", "evaluator.runtime.candidate")
    if variant != "uv":
        raise RuntimeConfigError("evaluator.runtime.candidate.variant must be uv")
    project = _string(raw, "project", "evaluator.runtime.candidate")
    relative = PurePosixPath(project)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise RuntimeConfigError("evaluator.runtime.candidate.project must stay inside the candidate")
    python = _string(raw, "python", "evaluator.runtime.candidate")
    if _PYTHON_VERSION.fullmatch(python) is None:
        raise RuntimeConfigError("evaluator.runtime.candidate.python must be a major.minor version")
    return CandidateRuntimeConfig(variant, relative.as_posix(), python)


def _proxy(value: object) -> ProxyRoutingConfig | None:
    if value is None:
        return None
    raw = _mapping(value, "evaluator.runtime.proxy")
    if set(raw) != {"mode", "model_endpoint"}:
        raise RuntimeConfigError("evaluator.runtime.proxy fields must be mode and model_endpoint")
    try:
        mode = ProxyMode(_string(raw, "mode", "evaluator.runtime.proxy"))
    except ValueError as error:
        raise RuntimeConfigError("evaluator.runtime.proxy.mode must be optional or required") from error
    try:
        route = ModelEndpointRoute(_string(raw, "model_endpoint", "evaluator.runtime.proxy"))
    except ValueError as error:
        raise RuntimeConfigError("evaluator.runtime.proxy.model_endpoint must be bypass") from error
    return ProxyRoutingConfig(mode, route)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise RuntimeConfigError(f"{field} must be a mapping with string keys")
    return cast("Mapping[str, object]", value)


def _string(payload: Mapping[str, object], field: str, parent: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise RuntimeConfigError(f"{parent}.{field} must be a non-empty string")
    return value


def _sha256(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RuntimeConfigError(f"resolved runtime {field} must be a SHA-256 digest")
    return value


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
