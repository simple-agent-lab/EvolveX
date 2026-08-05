from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from .runtime_auth import (
    AuthenticationErrorCode,
    RuntimeAuthenticationError,
    resolve_authentication,
)
from .runtime_profiles import (
    ResolvedRuntimeProfileV1,
    RuntimeProfileResolutionError,
    is_protected_runtime_environment_name,
    load_resolved_runtime_profile,
    model_endpoint_digest,
)


class RuntimeEnvironmentErrorCode(StrEnum):
    AUTHENTICATION_INVALID = "authentication_invalid"
    AUTH_JSON_MISSING = "auth_json_missing"
    AUTH_JSON_UNSUPPORTED = "auth_json_unsupported"
    CREDENTIAL_FORBIDDEN = "credential_forbidden"
    CREDENTIAL_MISSING = "credential_missing"
    ENDPOINT_INVALID = "endpoint_invalid"
    OVERRIDE_INVALID = "override_invalid"
    PROFILE_INVALID = "profile_invalid"


class RuntimeEnvironmentResolutionError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: RuntimeEnvironmentErrorCode = RuntimeEnvironmentErrorCode.OVERRIDE_INVALID,
    ):
        self.code = code
        super().__init__(message)


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


_PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_HARBOR_TEMPLATE = re.compile(r"\$\{EVOLVE_RUNTIME_[A-Z0-9_]+\}")


def resolve_runtime_environment(
    profile: ResolvedRuntimeProfileV1,
    environment: Mapping[str, str],
    *,
    agent_kind: str = "codex",
    meta_agent_kind: str | None = None,
    agent_overrides: Mapping[str, object] | None = None,
    verifier_overrides: Mapping[str, object] | None = None,
) -> RuntimeEnvironmentPlan:
    source = _source_environment(environment)
    if "CODEX_FORCE_AUTH_JSON" in source:
        raise RuntimeEnvironmentResolutionError(
            "CODEX_FORCE_AUTH_JSON is unsupported; configure CODEX_AUTH_JSON_PATH explicitly",
            code=RuntimeEnvironmentErrorCode.CREDENTIAL_FORBIDDEN,
        )
    _verify_endpoint(profile, source)
    process: dict[str, str] = {}
    role_values = {role: {} for role in RuntimeRole}

    agent_auth = _authentication(agent_kind, source)
    _add_environment(process, role_values[RuntimeRole.AGENT], RuntimeRole.AGENT, agent_auth)
    if meta_agent_kind is not None:
        meta_auth = _authentication(meta_agent_kind, source)
        _add_environment(
            process,
            role_values[RuntimeRole.META_AGENT],
            RuntimeRole.META_AGENT,
            meta_auth,
        )

    _add_standard_proxies(process, role_values, source)
    _apply_overrides(
        process, role_values[RuntimeRole.AGENT], RuntimeRole.AGENT, agent_overrides
    )
    if meta_agent_kind is not None:
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
        "endpoint_digest": profile.endpoint_digest,
        "proxy_policy": "standard-passthrough",
        "forwarded_names_by_role": {
            role.value: sorted(role_values[role]) for role in RuntimeRole
        },
    }
    return _plan(process, role_values, evidence)


def resolve_evaluator_runtime_environment(
    checkout: Path,
    evaluator: Mapping[str, object],
    environment: Mapping[str, str],
) -> RuntimeEnvironmentPlan:
    agent_kind = str(evaluator.get("agent") or "")
    profile_path = checkout / "evaluator" / "runtime-profile.json"
    if not profile_path.is_file():
        return resolve_legacy_runtime_environment(
            environment,
            agent_kind=agent_kind,
            agent_overrides=_mapping(evaluator.get("agent_env"), "evaluator.agent_env"),
            verifier_overrides=_mapping(evaluator.get("verifier_env"), "evaluator.verifier_env"),
        )
    try:
        profile = load_resolved_runtime_profile(json.loads(profile_path.read_text()))
    except (OSError, json.JSONDecodeError, RuntimeProfileResolutionError) as error:
        raise RuntimeEnvironmentResolutionError(
            "evaluator/runtime-profile.json is invalid",
            code=RuntimeEnvironmentErrorCode.PROFILE_INVALID,
        ) from error
    return resolve_runtime_environment(
        profile,
        environment,
        agent_kind=agent_kind,
        agent_overrides=_mapping(evaluator.get("agent_env"), "evaluator.agent_env"),
        verifier_overrides=_mapping(evaluator.get("verifier_env"), "evaluator.verifier_env"),
    )


def resolve_legacy_runtime_environment(
    environment: Mapping[str, str],
    *,
    agent_kind: str = "codex",
    agent_overrides: Mapping[str, object] | None = None,
    verifier_overrides: Mapping[str, object] | None = None,
) -> RuntimeEnvironmentPlan:
    source = _source_environment(environment)
    if "CODEX_FORCE_AUTH_JSON" in source:
        raise RuntimeEnvironmentResolutionError(
            "CODEX_FORCE_AUTH_JSON is unsupported; configure CODEX_AUTH_JSON_PATH explicitly",
            code=RuntimeEnvironmentErrorCode.CREDENTIAL_FORBIDDEN,
        )
    process: dict[str, str] = {}
    role_values = {role: {} for role in RuntimeRole}
    if source.get("OPENAI_API_KEY") or source.get("CODEX_AUTH_JSON_PATH"):
        authentication = _authentication(agent_kind, source)
        _add_environment(
            process,
            role_values[RuntimeRole.AGENT],
            RuntimeRole.AGENT,
            authentication,
        )
    _add_standard_proxies(process, role_values, source)
    _apply_overrides(
        process, role_values[RuntimeRole.AGENT], RuntimeRole.AGENT, agent_overrides
    )
    _apply_overrides(
        process,
        role_values[RuntimeRole.VERIFIER],
        RuntimeRole.VERIFIER,
        verifier_overrides,
    )
    evidence: dict[str, object] = {
        "schema_version": 1,
        "profile_name": "legacy-unverified",
        "proxy_policy": "standard-passthrough",
        "forwarded_names_by_role": {
            role.value: sorted(role_values[role]) for role in RuntimeRole
        },
    }
    return _plan(process, role_values, evidence)


def write_harbor_environment_inputs(run_dir: Path, plan: RuntimeEnvironmentPlan) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_atomic(run_dir / "runtime-agent.env", _environment_file(plan.agent_env()))
    _write_atomic(run_dir / "runtime-verifier.env", _environment_file(plan.verifier_env()))
    evidence = json.dumps(plan.persisted_payload(), indent=2, sort_keys=True) + "\n"
    _write_atomic(run_dir / "runtime-environment-evidence.json", evidence)


def _verify_endpoint(
    profile: ResolvedRuntimeProfileV1, source: Mapping[str, str]
) -> None:
    try:
        current = model_endpoint_digest(source.get("OPENAI_BASE_URL"))
    except RuntimeProfileResolutionError as error:
        raise RuntimeEnvironmentResolutionError(
            str(error), code=RuntimeEnvironmentErrorCode.ENDPOINT_INVALID
        ) from error
    if current != profile.endpoint_digest:
        raise RuntimeEnvironmentResolutionError(
            "OPENAI_BASE_URL endpoint digest does not match the resolved runtime profile",
            code=RuntimeEnvironmentErrorCode.ENDPOINT_INVALID,
        )


def _authentication(agent_kind: str, source: Mapping[str, str]) -> dict[str, str]:
    try:
        return resolve_authentication(agent_kind, source).environment()
    except RuntimeAuthenticationError as error:
        code = {
            AuthenticationErrorCode.CREDENTIAL_MISSING: RuntimeEnvironmentErrorCode.CREDENTIAL_MISSING,
            AuthenticationErrorCode.AUTH_JSON_MISSING: RuntimeEnvironmentErrorCode.AUTH_JSON_MISSING,
            AuthenticationErrorCode.AUTH_JSON_UNSUPPORTED: RuntimeEnvironmentErrorCode.AUTH_JSON_UNSUPPORTED,
        }[error.code]
        raise RuntimeEnvironmentResolutionError(
            str(error), code=code
        ) from error


def _add_standard_proxies(
    process: dict[str, str],
    role_values: dict[RuntimeRole, dict[str, str]],
    source: Mapping[str, str],
) -> None:
    for name in _PROXY_NAMES:
        if value := source.get(name):
            checked = _single_line_value(name, value)
            for role in RuntimeRole:
                _add_value(process, role_values[role], role, name, checked)


def _add_environment(
    process: dict[str, str],
    target: dict[str, str],
    role: RuntimeRole,
    environment: Mapping[str, str],
) -> None:
    for name, value in environment.items():
        _add_value(process, target, role, name, value)


def _plan(
    process: dict[str, str],
    role_values: dict[RuntimeRole, dict[str, str]],
    evidence: Mapping[str, object],
) -> RuntimeEnvironmentPlan:
    return RuntimeEnvironmentPlan(
        process_environment=tuple(sorted(process.items())),
        agent_environment=tuple(sorted(role_values[RuntimeRole.AGENT].items())),
        verifier_environment=tuple(sorted(role_values[RuntimeRole.VERIFIER].items())),
        meta_agent_environment=tuple(sorted(role_values[RuntimeRole.META_AGENT].items())),
        evidence=tuple(sorted(evidence.items())),
    )


def _source_environment(environment: Mapping[str, str]) -> dict[str, str]:
    source: dict[str, str] = {}
    for name, value in environment.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise RuntimeEnvironmentResolutionError(
                "runtime environment names and values must be strings"
            )
        source[name] = value
    return source


def _mapping(value: object, field: str) -> Mapping[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise RuntimeEnvironmentResolutionError(f"{field} must be a mapping")
    return cast("Mapping[str, object]", value)


def _single_line_value(name: str, value: str) -> str:
    if "\0" in value or "\n" in value or "\r" in value:
        raise RuntimeEnvironmentResolutionError(
            f"runtime environment value for {name} must be single-line"
        )
    return value


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
            raise RuntimeEnvironmentResolutionError(
                f"runtime override must not configure protected name {name}"
            )
        _add_value(process, target, role, name, _scalar_value(name, raw))


def _scalar_value(name: str, raw: object) -> str:
    if isinstance(raw, bool):
        value = "true" if raw else "false"
    elif isinstance(raw, (str, int, float)):
        value = str(raw)
    else:
        raise RuntimeEnvironmentResolutionError(
            f"runtime override for {name} must be scalar"
        )
    if "\0" in value or "\n" in value or "\r" in value:
        raise RuntimeEnvironmentResolutionError(
            f"runtime override for {name} must be single-line"
        )
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
        raise RuntimeEnvironmentResolutionError(
            f"runtime environment aliases disagree for {name}"
        )
    process[internal_name] = value
    target[name] = f"${{{internal_name}}}"


def _environment_file(environment: Mapping[str, str]) -> str:
    lines: list[str] = []
    for name, value in sorted(environment.items()):
        if _ENVIRONMENT_NAME.fullmatch(name) is None:
            raise RuntimeEnvironmentResolutionError(
                f"invalid Harbor environment name: {name!r}"
            )
        if _HARBOR_TEMPLATE.fullmatch(value) is None:
            raise RuntimeEnvironmentResolutionError(
                f"Harbor environment value for {name} must be a single Harbor environment template"
            )
        lines.append(f"{name}={value}\n")
    return "".join(lines)


def _write_atomic(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.chmod(0o600)
    temporary.replace(path)
