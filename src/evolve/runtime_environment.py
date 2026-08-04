from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from .runtime_profiles import (
    ResolvedRuntimeProfileV1,
    RuntimeProfileResolutionError,
    is_protected_runtime_environment_name,
    load_resolved_runtime_profile,
    model_route_digest,
    normalize_model_route,
)


class RuntimeEnvironmentResolutionError(ValueError):
    pass


class RuntimeRole(StrEnum):
    AGENT = "agent"
    VERIFIER = "verifier"
    META_AGENT = "meta_agent"


@dataclass(frozen=True)
class RuntimeEnvironmentPlan:
    process_environment: tuple[tuple[str, str], ...]
    agent_environment: tuple[tuple[str, str], ...]
    verifier_environment: tuple[tuple[str, str], ...]
    meta_agent_environment: tuple[tuple[str, str], ...]
    evidence: tuple[tuple[str, object], ...]

    def process_env(self) -> dict[str, str]:
        return dict(self.process_environment)

    def agent_env(self) -> dict[str, str]:
        return dict(self.agent_environment)

    def verifier_env(self) -> dict[str, str]:
        return dict(self.verifier_environment)

    def meta_agent_env(self) -> dict[str, str]:
        return dict(self.meta_agent_environment)

    def persisted_payload(self) -> dict[str, object]:
        return {
            "agent_environment": self.agent_env(),
            "verifier_environment": self.verifier_env(),
            "meta_agent_environment": self.meta_agent_env(),
            "evidence": dict(self.evidence),
        }


_PROXY_ALIASES = (
    ("HTTP_PROXY", "http_proxy"),
    ("HTTPS_PROXY", "https_proxy"),
    ("ALL_PROXY", "all_proxy"),
    ("NO_PROXY", "no_proxy"),
)
_DEPENDENCY_HOSTS = {
    "astral.sh",
    "download.pytorch.org",
    "files.pythonhosted.org",
    "github.com",
    "objects.githubusercontent.com",
    "pypi.org",
}
_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_HARBOR_TEMPLATE = re.compile(r"\$\{EVOLVE_RUNTIME_[A-Z0-9_]+\}")
_FORBIDDEN_FILE_AUTH = ("CODEX_AUTH_JSON_PATH", "CODEX_FORCE_AUTH_JSON")
_LEGACY_AGENT_CREDENTIALS = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE")
_LEGACY_PROXY_NAMES = frozenset(name for aliases in _PROXY_ALIASES for name in aliases)


def resolve_runtime_environment(
    profile: ResolvedRuntimeProfileV1,
    environment: Mapping[str, str],
    *,
    agent_overrides: Mapping[str, object] | None = None,
    verifier_overrides: Mapping[str, object] | None = None,
) -> RuntimeEnvironmentPlan:
    source = _source_environment(environment)
    _reject_forbidden_credentials(profile, source)
    route = _required_value(source, "OPENAI_BASE_URL")
    try:
        normalized_route = normalize_model_route(route)
        current_route_digest = model_route_digest(route)
    except RuntimeProfileResolutionError as error:
        raise RuntimeEnvironmentResolutionError(str(error)) from error
    if current_route_digest != profile.model_route_digest:
        raise RuntimeEnvironmentResolutionError(
            "OPENAI_BASE_URL route digest does not match the resolved runtime profile"
        )
    model_hostname = urlsplit(normalized_route).hostname
    if not model_hostname:
        raise RuntimeEnvironmentResolutionError("OPENAI_BASE_URL has no model hostname")

    proxy_values = _normalized_proxy_values(source, model_hostname)
    process: dict[str, str] = {}
    role_values: dict[RuntimeRole, dict[str, str]] = {
        role: {} for role in RuntimeRole
    }
    required_by_role = dict(profile.profile.required_credentials_by_role)
    for role_name, names in profile.profile.required_credentials_by_role:
        try:
            role = RuntimeRole(role_name)
        except ValueError as error:
            raise RuntimeEnvironmentResolutionError(
                f"runtime profile contains unknown credential role {role_name}"
            ) from error
        for name in names:
            _add_value(process, role_values[role], role, name, _required_value(source, name))

    for role in RuntimeRole:
        for names, value in proxy_values:
            for name in names:
                _add_value(process, role_values[role], role, name, value)

    _apply_overrides(process, role_values[RuntimeRole.AGENT], RuntimeRole.AGENT, agent_overrides)
    _apply_overrides(
        process,
        role_values[RuntimeRole.META_AGENT],
        RuntimeRole.META_AGENT,
        agent_overrides,
    )
    _apply_overrides(
        process,
        role_values[RuntimeRole.VERIFIER],
        RuntimeRole.VERIFIER,
        verifier_overrides,
    )

    evidence: dict[str, object] = {
        "schema_version": 1,
        "profile_name": profile.profile.name,
        "profile_digest": profile.profile_digest,
        "model_route": profile.profile.model_route,
        "model_route_digest": profile.model_route_digest,
        "proxy_policy": profile.profile.proxy_policy,
        "model_bypass_policy": profile.profile.model_bypass_policy,
        "required_credential_names_by_role": {
            role: list(names) for role, names in required_by_role.items()
        },
        "forwarded_names_by_role": {
            role.value: sorted(role_values[role]) for role in RuntimeRole
        },
    }
    return RuntimeEnvironmentPlan(
        process_environment=tuple(sorted(process.items())),
        agent_environment=tuple(sorted(role_values[RuntimeRole.AGENT].items())),
        verifier_environment=tuple(sorted(role_values[RuntimeRole.VERIFIER].items())),
        meta_agent_environment=tuple(sorted(role_values[RuntimeRole.META_AGENT].items())),
        evidence=tuple(sorted(evidence.items())),
    )


def resolve_evaluator_runtime_environment(
    checkout: Path,
    evaluator: Mapping[str, object],
    environment: Mapping[str, str],
) -> RuntimeEnvironmentPlan:
    profile_path = checkout / "evaluator" / "runtime-profile.json"
    if not profile_path.is_file():
        return resolve_legacy_runtime_environment(
            environment,
            agent_overrides=_mapping(evaluator.get("agent_env"), "evaluator.agent_env"),
            verifier_overrides=_mapping(evaluator.get("verifier_env"), "evaluator.verifier_env"),
        )
    try:
        profile = load_resolved_runtime_profile(json.loads(profile_path.read_text()))
    except json.JSONDecodeError as error:
        raise RuntimeEnvironmentResolutionError(
            "evaluator/runtime-profile.json is invalid JSON"
        ) from error
    return resolve_runtime_environment(
        profile,
        environment,
        agent_overrides=_mapping(evaluator.get("agent_env"), "evaluator.agent_env"),
        verifier_overrides=_mapping(evaluator.get("verifier_env"), "evaluator.verifier_env"),
    )


def resolve_legacy_runtime_environment(
    environment: Mapping[str, str],
    *,
    agent_overrides: Mapping[str, object] | None = None,
    verifier_overrides: Mapping[str, object] | None = None,
) -> RuntimeEnvironmentPlan:
    source = _source_environment(environment)
    _reject_legacy_file_auth(source, agent_overrides, verifier_overrides)
    process: dict[str, str] = {}
    agent: dict[str, str] = {}
    verifier: dict[str, str] = {}
    for name in _LEGACY_AGENT_CREDENTIALS:
        if source.get(name):
            _add_value(process, agent, RuntimeRole.AGENT, name, _single_line_value(name, source[name]))
    _apply_legacy_overrides(process, agent, RuntimeRole.AGENT, agent_overrides)
    _apply_legacy_overrides(process, verifier, RuntimeRole.VERIFIER, verifier_overrides)
    model_hostname = _legacy_model_hostname(source, agent_overrides)
    for aliases, value in _legacy_proxy_values(source, agent_overrides, model_hostname):
        for name in aliases:
            _add_value(process, agent, RuntimeRole.AGENT, name, value)
            _add_value(process, verifier, RuntimeRole.VERIFIER, name, value)
    evidence: dict[str, object] = {
        "schema_version": 1,
        "profile_name": "legacy-unverified",
        "forwarded_names_by_role": {
            RuntimeRole.AGENT.value: sorted(agent),
            RuntimeRole.VERIFIER.value: sorted(verifier),
            RuntimeRole.META_AGENT.value: [],
        },
    }
    return RuntimeEnvironmentPlan(
        process_environment=tuple(sorted(process.items())),
        agent_environment=tuple(sorted(agent.items())),
        verifier_environment=tuple(sorted(verifier.items())),
        meta_agent_environment=(),
        evidence=tuple(sorted(evidence.items())),
    )


def write_harbor_environment_inputs(run_dir: Path, plan: RuntimeEnvironmentPlan) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_atomic(run_dir / "runtime-agent.env", _environment_file(plan.agent_env()))
    _write_atomic(run_dir / "runtime-verifier.env", _environment_file(plan.verifier_env()))
    evidence = json.dumps(plan.persisted_payload(), indent=2, sort_keys=True) + "\n"
    _write_atomic(run_dir / "runtime-environment-evidence.json", evidence)


def _source_environment(environment: Mapping[str, str]) -> dict[str, str]:
    source: dict[str, str] = {}
    for name, value in environment.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise RuntimeEnvironmentResolutionError("runtime environment names and values must be strings")
        source[name] = value
    return source


def _mapping(value: object, field: str) -> Mapping[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise RuntimeEnvironmentResolutionError(f"{field} must be a mapping")
    return cast(Mapping[str, object], value)


def _reject_legacy_file_auth(
    source: Mapping[str, str],
    agent_overrides: Mapping[str, object] | None,
    verifier_overrides: Mapping[str, object] | None,
) -> None:
    configured = set(source) | set(agent_overrides or ()) | set(verifier_overrides or ())
    for name in _FORBIDDEN_FILE_AUTH:
        if name in configured:
            raise RuntimeEnvironmentResolutionError(f"forbidden credential variable is present: {name}")


def _apply_legacy_overrides(
    process: dict[str, str],
    target: dict[str, str],
    role: RuntimeRole,
    overrides: Mapping[str, object] | None,
) -> None:
    if overrides is None:
        return
    for name, raw in overrides.items():
        if not isinstance(name, str) or _ENVIRONMENT_NAME.fullmatch(name) is None:
            raise RuntimeEnvironmentResolutionError(f"invalid runtime override name: {name!r}")
        if name not in _LEGACY_PROXY_NAMES:
            _add_value(process, target, role, name, _scalar_value(name, raw))


def _legacy_model_hostname(
    source: Mapping[str, str], agent_overrides: Mapping[str, object] | None
) -> str | None:
    overrides = agent_overrides or {}
    raw = overrides.get("OPENAI_BASE_URL") or overrides.get("OPENAI_API_BASE")
    value = str(raw) if raw is not None else source.get("OPENAI_BASE_URL") or source.get("OPENAI_API_BASE")
    if not value:
        return None
    hostname = urlsplit(_single_line_value("OPENAI_BASE_URL", value)).hostname
    if not hostname:
        raise RuntimeEnvironmentResolutionError("configured model base URL has no hostname")
    return hostname.lower()


def _legacy_proxy_values(
    source: Mapping[str, str],
    agent_overrides: Mapping[str, object] | None,
    model_hostname: str | None,
) -> tuple[tuple[tuple[str, str], str], ...]:
    overrides = agent_overrides or {}
    values: list[tuple[tuple[str, str], str]] = []
    explicit_names = (
        "EVOLVE_HARBOR_HTTP_PROXY",
        "EVOLVE_HARBOR_HTTPS_PROXY",
        "EVOLVE_HARBOR_ALL_PROXY",
    )
    for aliases, explicit in zip(_PROXY_ALIASES[:3], explicit_names, strict=True):
        raw = source.get(explicit) or overrides.get(aliases[1]) or overrides.get(aliases[0])
        raw = raw or source.get(aliases[1]) or source.get(aliases[0])
        if raw:
            values.append((aliases, _single_line_value(aliases[0], str(raw))))
    bypass_override = source.get("EVOLVE_HARBOR_NO_PROXY")
    agent_bypass = overrides.get("no_proxy") or overrides.get("NO_PROXY")
    configured = str(bypass_override or agent_bypass) if bypass_override or agent_bypass else ",".join(
        value for value in (source.get("no_proxy"), source.get("NO_PROXY")) if value
    )
    bypass = _model_bypass(configured or None, model_hostname)
    if bypass:
        values.append((_PROXY_ALIASES[-1], bypass))
    return tuple(values)


def _reject_forbidden_credentials(
    profile: ResolvedRuntimeProfileV1, source: Mapping[str, str]
) -> None:
    for name in profile.profile.forbidden_credentials:
        if name in source:
            raise RuntimeEnvironmentResolutionError(f"forbidden credential variable is present: {name}")


def _required_value(source: Mapping[str, str], name: str) -> str:
    value = source.get(name)
    if value is None or not value.strip():
        raise RuntimeEnvironmentResolutionError(f"required runtime credential is missing: {name}")
    return _single_line_value(name, value)


def _normalized_proxy_values(
    source: Mapping[str, str], model_hostname: str
) -> tuple[tuple[tuple[str, str], str], ...]:
    normalized: list[tuple[tuple[str, str], str]] = []
    for aliases in _PROXY_ALIASES[:-1]:
        value = _alias_value(source, aliases)
        if value is not None:
            normalized.append((aliases, value))
    bypass = _model_bypass(_alias_value(source, _PROXY_ALIASES[-1]), model_hostname)
    normalized.append((_PROXY_ALIASES[-1], bypass))
    return tuple(normalized)


def _alias_value(source: Mapping[str, str], aliases: tuple[str, str]) -> str | None:
    configured = {
        _single_line_value(name, source[name]) for name in aliases if source.get(name)
    }
    if len(configured) > 1:
        raise RuntimeEnvironmentResolutionError(f"{aliases[0]} aliases disagree")
    return next(iter(configured), None)


def _single_line_value(name: str, value: str) -> str:
    if "\0" in value or "\n" in value or "\r" in value:
        raise RuntimeEnvironmentResolutionError(f"runtime environment value for {name} must be single-line")
    return value


def _model_bypass(configured: str | None, model_hostname: str | None) -> str:
    entries = [entry.strip() for entry in (configured or "").split(",") if entry.strip()]
    filtered = [entry for entry in entries if not _dependency_host(entry)]
    if model_hostname and model_hostname.lower() not in {
        entry.lstrip(".").lower() for entry in filtered
    }:
        filtered.append(model_hostname.lower())
    return ",".join(filtered)


def _dependency_host(entry: str) -> bool:
    candidate = entry.lstrip(".").lower()
    return any(candidate == host or candidate.endswith(f".{host}") for host in _DEPENDENCY_HOSTS)


def _apply_overrides(
    process: dict[str, str],
    target: dict[str, str],
    role: RuntimeRole,
    overrides: Mapping[str, object] | None,
) -> None:
    if overrides is None:
        return
    seen: set[str] = set()
    for name, raw in overrides.items():
        if not isinstance(name, str) or _ENVIRONMENT_NAME.fullmatch(name) is None:
            raise RuntimeEnvironmentResolutionError(f"invalid runtime override name: {name!r}")
        canonical_name = name.upper()
        if canonical_name in seen:
            raise RuntimeEnvironmentResolutionError(f"duplicate runtime override name: {name}")
        seen.add(canonical_name)
        if is_protected_runtime_environment_name(name):
            raise RuntimeEnvironmentResolutionError(f"runtime override must not configure protected name {name}")
        value = _scalar_value(name, raw)
        _add_value(process, target, role, name, value)


def _scalar_value(name: str, raw: object) -> str:
    if isinstance(raw, bool):
        value = "true" if raw else "false"
    elif isinstance(raw, (str, int, float)):
        value = str(raw)
    else:
        raise RuntimeEnvironmentResolutionError(f"runtime override for {name} must be scalar")
    if "\0" in value or "\n" in value or "\r" in value:
        raise RuntimeEnvironmentResolutionError(f"runtime override for {name} must be single-line")
    return value


def _add_value(
    process: dict[str, str],
    target: dict[str, str],
    role: RuntimeRole,
    name: str,
    value: str,
) -> None:
    internal_name = f"EVOLVE_RUNTIME_{role.value.upper()}_{name.upper()}"
    existing = process.get(internal_name)
    if existing is not None and existing != value:
        raise RuntimeEnvironmentResolutionError(f"runtime environment aliases disagree for {name}")
    process[internal_name] = value
    target[name] = f"${{{internal_name}}}"


def _environment_file(environment: Mapping[str, str]) -> str:
    lines: list[str] = []
    for name, value in sorted(environment.items()):
        if _ENVIRONMENT_NAME.fullmatch(name) is None or "=" in name or "\n" in name or "\r" in name:
            raise RuntimeEnvironmentResolutionError(f"invalid Harbor environment name: {name!r}")
        if _HARBOR_TEMPLATE.fullmatch(value) is None:
            raise RuntimeEnvironmentResolutionError(
                f"Harbor environment value for {name} must be a single Harbor environment template"
            )
        lines.append(f"{name}={value}\n")
    return "".join(lines)


def _write_atomic(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)
