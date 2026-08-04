from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from .candidate.smoke import SmokeMode, SmokeResult, run_candidate_smoke
from .evaluation.contract import (
    ContractResolutionContext,
    EvaluationContractResolutionError,
    resolve_evaluation_contract,
    trusted_evaluator_config,
)
from .git import git
from .host_runtime import uv_executable
from .runtime import reserve_attempt_directory
from .runtime_environment import (
    RuntimeEnvironmentResolutionError,
    resolve_runtime_environment,
)
from .runtime_profiles import (
    ResolvedRuntimeProfileV1,
    RuntimeProfileResolutionError,
    load_resolved_runtime_profile,
)


class PreflightMode(StrEnum):
    ORDINARY = "ordinary"
    SMOKE = "smoke"


class PreflightStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class PreflightCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class PreflightFailureCategory(StrEnum):
    CONFIGURATION_INVALID = "configuration_invalid"
    RUNTIME_PROFILE_INVALID = "runtime_profile_invalid"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    DEPENDENCY_LOCK_INVALID = "dependency_lock_invalid"
    DEPENDENCY_TOOL_UNAVAILABLE = "dependency_tool_unavailable"
    CREDENTIAL_MISSING = "credential_missing"
    CREDENTIAL_FORBIDDEN = "credential_forbidden"
    ENDPOINT_INVALID = "endpoint_invalid"
    CONTAINER_IMAGE_UNAVAILABLE = "container_image_unavailable"
    NETWORK_UNAVAILABLE = "network_unavailable"
    MODEL_SMOKE_FAILED = "model_smoke_failed"


@dataclass(frozen=True)
class ArtifactReferenceV1:
    path: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True)
class PreflightCheckV1:
    name: str
    status: PreflightCheckStatus
    failure_category: PreflightFailureCategory | None = None
    message: str = ""
    artifact: ArtifactReferenceV1 | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
        }
        if self.failure_category is not None:
            payload["failure_category"] = self.failure_category.value
        if self.artifact is not None:
            payload["artifact"] = self.artifact.to_dict()
        return payload


@dataclass(frozen=True)
class PreflightResultV1:
    schema_version: int
    status: PreflightStatus
    profile_name: str
    profile_digest: str
    runtime_digest: str
    model_route_digest: str
    mode: PreflightMode
    checks: tuple[PreflightCheckV1, ...]
    required_credential_names_by_role: tuple[tuple[str, tuple[str, ...]], ...]
    failure_category: PreflightFailureCategory | None = None
    failure_message: str | None = None
    receipt_path: Path | None = field(default=None, compare=False)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "profile_name": self.profile_name,
            "profile_digest": self.profile_digest,
            "runtime_digest": self.runtime_digest,
            "model_route_digest": self.model_route_digest,
            "mode": self.mode.value,
            "checks": [check.to_dict() for check in self.checks],
            "required_credential_names_by_role": {
                role: list(names) for role, names in self.required_credential_names_by_role
            },
        }
        if self.failure_category is not None:
            payload["failure_category"] = self.failure_category.value
        if self.failure_message is not None:
            payload["failure_message"] = self.failure_message
        return payload

    def write(self) -> Path:
        if self.receipt_path is None:
            raise ValueError("preflight receipt path is not configured")
        self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.receipt_path.with_suffix(self.receipt_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
        temporary.replace(self.receipt_path)
        return self.receipt_path

    @classmethod
    def failed(
        cls,
        *,
        mode: PreflightMode,
        profile_name: str,
        profile_digest: str,
        runtime_digest: str,
        model_route_digest: str,
        checks: tuple[PreflightCheckV1, ...],
        category: PreflightFailureCategory,
        message: str,
        receipt_path: Path | None = None,
        required_credential_names_by_role: tuple[tuple[str, tuple[str, ...]], ...] = (),
    ) -> PreflightResultV1:
        return cls(
            schema_version=1,
            status=PreflightStatus.FAILED,
            profile_name=profile_name,
            profile_digest=profile_digest,
            runtime_digest=runtime_digest,
            model_route_digest=model_route_digest,
            mode=mode,
            checks=checks,
            required_credential_names_by_role=required_credential_names_by_role,
            failure_category=category,
            failure_message=message,
            receipt_path=receipt_path,
        )


_SENSITIVE_ENVIRONMENT_NAME = re.compile(
    r"(?i)(?:api[_-]?key|secret|token|password|credential|authorization|proxy|base[_-]?url|endpoint)"
)


def run_preflight(
    workspace: Path,
    *,
    mode: PreflightMode = PreflightMode.ORDINARY,
    candidate_commit: str | None = None,
    candidate_checkout: Path | None = None,
    purpose: str = "candidate",
    task_limit: int | None = None,
    receipt_path: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> PreflightResultV1:
    root = workspace.resolve()
    candidate_root = (candidate_checkout or root).resolve()
    source_environment = dict(os.environ if environment is None else environment)
    destination = receipt_path or _next_receipt_path(root)
    checks: list[PreflightCheckV1] = []
    profile: ResolvedRuntimeProfileV1 | None = None
    profile_name = "unknown"
    profile_digest = ""
    runtime_digest = ""
    route_digest = ""
    required_credentials: tuple[tuple[str, tuple[str, ...]], ...] = ()

    try:
        evaluator = trusted_evaluator_config(root)
        configured_profile = _configured_profile_name(evaluator)
    except (EvaluationContractResolutionError, ValueError) as error:
        return _failed_result(
            mode,
            destination,
            checks,
            "configuration",
            PreflightFailureCategory.CONFIGURATION_INVALID,
            str(error),
            source_environment,
        )
    checks.append(_passed_check("configuration"))

    try:
        profile = _trusted_profile(root)
        if profile.profile.name != configured_profile:
            raise RuntimeProfileResolutionError(
                "resolved profile name does not match evaluator.runtime.profile"
            )
    except (RuntimeProfileResolutionError, ValueError) as error:
        return _failed_result(
            mode,
            destination,
            checks,
            "runtime_profile",
            PreflightFailureCategory.RUNTIME_PROFILE_INVALID,
            str(error),
            source_environment,
        )
    profile_name = profile.profile.name
    profile_digest = profile.profile_digest
    runtime_digest = profile.runtime_digest
    route_digest = profile.model_route_digest
    required_credentials = profile.profile.required_credentials_by_role
    checks.append(_passed_check("runtime_profile"))

    pinned_runtime = _git_text(root, "gen/0:evaluator/runtime.pin")
    if not pinned_runtime or pinned_runtime.strip() != profile.runtime_digest:
        return _failed_result(
            mode,
            destination,
            checks,
            "runtime_digest",
            PreflightFailureCategory.RUNTIME_UNAVAILABLE,
            "runtime.pin does not match the resolved runtime profile",
            source_environment,
            profile,
        )
    checks.append(_passed_check("runtime_digest"))

    try:
        resolve_evaluation_contract(
            ContractResolutionContext(
                workspace=root,
                candidate_commit=candidate_commit or "gen/0",
                purpose=purpose,
                generation="preflight",
                task_limit=task_limit,
            )
        )
    except EvaluationContractResolutionError as error:
        return _failed_result(
            mode,
            destination,
            checks,
            "evaluation_contract",
            PreflightFailureCategory.CONFIGURATION_INVALID,
            str(error),
            source_environment,
            profile,
        )
    checks.append(_passed_check("evaluation_contract"))

    for tool in profile.profile.required_tools:
        if not _tool_available(tool, source_environment):
            return _failed_result(
                mode,
                destination,
                checks,
                "dependency_tools",
                PreflightFailureCategory.DEPENDENCY_TOOL_UNAVAILABLE,
                f"required dependency tool is unavailable: {tool}",
                source_environment,
                profile,
            )
    checks.append(_passed_check("dependency_tools"))

    if not _image_available(profile.runtime_digest, source_environment):
        return _failed_result(
            mode,
            destination,
            checks,
            "container_image",
            PreflightFailureCategory.CONTAINER_IMAGE_UNAVAILABLE,
            "the immutable evaluator container image is not available locally",
            source_environment,
            profile,
        )
    checks.append(_passed_check("container_image"))

    candidate_runtime = profile.profile.candidate_runtime
    if candidate_runtime is not None:
        project = candidate_root / candidate_runtime.project
        if not _lock_valid(project, source_environment):
            return _failed_result(
                mode,
                destination,
                checks,
                "dependency_lock",
                PreflightFailureCategory.DEPENDENCY_LOCK_INVALID,
                "candidate uv lock validation failed",
                source_environment,
                profile,
            )
        checks.append(_passed_check("dependency_lock"))

    try:
        resolve_runtime_environment(profile, source_environment)
    except RuntimeEnvironmentResolutionError as error:
        return _failed_result(
            mode,
            destination,
            checks,
            "runtime_environment",
            _environment_failure_category(str(error)),
            str(error),
            source_environment,
            profile,
        )
    checks.append(_passed_check("runtime_environment"))

    if mode is PreflightMode.SMOKE:
        try:
            smoke = run_candidate_smoke(
                root,
                workspace=root,
                mode=SmokeMode.MODEL,
                environment=source_environment,
            )
        except Exception as error:
            return _failed_result(
                mode,
                destination,
                checks,
                "model_agent_request",
                PreflightFailureCategory.MODEL_SMOKE_FAILED,
                str(error) or type(error).__name__,
                source_environment,
                profile,
            )
        smoke_artifact = artifact_reference(
            smoke.attempt_dir / "result.json",
            relative_to=root,
        )
        if smoke.status != "passed":
            category = _structured_smoke_failure_category(smoke)
            return _failed_result(
                mode,
                destination,
                checks,
                "model_agent_request",
                category or PreflightFailureCategory.MODEL_SMOKE_FAILED,
                _smoke_failure_message(smoke),
                source_environment,
                profile,
                artifact=smoke_artifact,
            )
        checks.append(
            PreflightCheckV1(
                name="model_agent_request",
                status=PreflightCheckStatus.PASSED,
                artifact=smoke_artifact,
            )
        )

    result = PreflightResultV1(
        schema_version=1,
        status=PreflightStatus.PASSED,
        profile_name=profile_name,
        profile_digest=profile_digest,
        runtime_digest=runtime_digest,
        model_route_digest=route_digest,
        mode=mode,
        checks=tuple(checks),
        required_credential_names_by_role=required_credentials,
        receipt_path=destination,
    )
    result.write()
    return result


def _failed_result(
    mode: PreflightMode,
    destination: Path,
    completed: list[PreflightCheckV1],
    check_name: str,
    category: PreflightFailureCategory,
    message: str,
    environment: Mapping[str, str],
    profile: ResolvedRuntimeProfileV1 | None = None,
    *,
    artifact: ArtifactReferenceV1 | None = None,
) -> PreflightResultV1:
    bounded = _bounded_message(message, environment)
    checks = (
        *completed,
        PreflightCheckV1(
            name=check_name,
            status=PreflightCheckStatus.FAILED,
            failure_category=category,
            message=bounded,
            artifact=artifact,
        ),
    )
    result = PreflightResultV1.failed(
        mode=mode,
        profile_name=profile.profile.name if profile is not None else "unknown",
        profile_digest=profile.profile_digest if profile is not None else "",
        runtime_digest=profile.runtime_digest if profile is not None else "",
        model_route_digest=profile.model_route_digest if profile is not None else "",
        checks=checks,
        category=category,
        message=bounded,
        receipt_path=destination,
        required_credential_names_by_role=(
            profile.profile.required_credentials_by_role if profile is not None else ()
        ),
    )
    result.write()
    return result


def _passed_check(name: str) -> PreflightCheckV1:
    return PreflightCheckV1(name=name, status=PreflightCheckStatus.PASSED)


def _structured_smoke_failure_category(
    smoke: SmokeResult,
) -> PreflightFailureCategory | None:
    try:
        payload = json.loads((smoke.attempt_dir / "result.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None
    category = payload.get("failure_category")
    if category == PreflightFailureCategory.NETWORK_UNAVAILABLE.value:
        return PreflightFailureCategory.NETWORK_UNAVAILABLE
    if category == PreflightFailureCategory.DEPENDENCY_TOOL_UNAVAILABLE.value:
        return PreflightFailureCategory.DEPENDENCY_TOOL_UNAVAILABLE
    return None


def _smoke_failure_message(smoke: SmokeResult) -> str:
    try:
        detail = smoke.stderr_path.read_text().strip()
    except OSError:
        detail = ""
    return detail or f"model smoke finished with status {smoke.status}"


def _configured_profile_name(evaluator: Mapping[str, object]) -> str:
    runtime = evaluator.get("runtime")
    if not isinstance(runtime, Mapping):
        raise ValueError("strict preflight requires evaluator.runtime.profile")
    unknown = sorted(str(name) for name in runtime if name != "profile")
    if unknown:
        raise ValueError("unknown evaluator.runtime fields: " + ", ".join(unknown))
    profile = runtime.get("profile")
    if not isinstance(profile, str) or not profile:
        raise ValueError("evaluator.runtime.profile must be a non-empty string")
    return profile


def _trusted_profile(workspace: Path) -> ResolvedRuntimeProfileV1:
    text = _git_text(workspace, "gen/0:evaluator/runtime-profile.json")
    if text is None:
        raise RuntimeProfileResolutionError("gen/0 runtime-profile.json is unavailable")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeProfileResolutionError("gen/0 runtime-profile.json is invalid JSON") from error
    return load_resolved_runtime_profile(payload)


def _git_text(workspace: Path, revision: str) -> str | None:
    result = git(workspace, "show", revision, check=False)
    return result.stdout if result.returncode == 0 else None


def _tool_available(name: str, environment: Mapping[str, str]) -> bool:
    return shutil.which(name, path=environment.get("PATH")) is not None


def _image_available(runtime_digest: str, environment: Mapping[str, str]) -> bool:
    docker = shutil.which("docker", path=environment.get("PATH"))
    if docker is None:
        return False
    return _local_command_succeeds([docker, "image", "inspect", runtime_digest], environment)


def _lock_valid(project: Path, environment: Mapping[str, str]) -> bool:
    if not (project / "pyproject.toml").is_file() or not (project / "uv.lock").is_file():
        return False
    try:
        uv = uv_executable(environment)
    except RuntimeError:
        return False
    return _local_command_succeeds(
        [
            uv,
            "--no-cache",
            "lock",
            "--offline",
            "--check",
            "--python",
            sys.executable,
            "--project",
            str(project),
        ],
        environment,
    )


def _local_command_succeeds(command: list[str], environment: Mapping[str, str]) -> bool:
    try:
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
            env={**os.environ, **environment},
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _environment_failure_category(message: str) -> PreflightFailureCategory:
    lowered = message.lower()
    if "forbidden credential" in lowered:
        return PreflightFailureCategory.CREDENTIAL_FORBIDDEN
    if "credential is missing" in lowered:
        return PreflightFailureCategory.CREDENTIAL_MISSING
    if "openai_base_url" in lowered or "route digest" in lowered or "model hostname" in lowered:
        return PreflightFailureCategory.ENDPOINT_INVALID
    return PreflightFailureCategory.CONFIGURATION_INVALID


def _bounded_message(message: str, environment: Mapping[str, str]) -> str:
    redacted = message
    values = {
        value
        for name, value in environment.items()
        if _SENSITIVE_ENVIRONMENT_NAME.search(name) and len(value) >= 4
    }
    for value in sorted(values, key=len, reverse=True):
        redacted = redacted.replace(value, "[REDACTED]")
    redacted = re.sub(r"(?i)https?://[^\s]+", "[REDACTED_URL]", redacted)
    return redacted[:500]


def _next_receipt_path(workspace: Path) -> Path:
    return reserve_attempt_directory(workspace / "runs" / "preflight") / "preflight.json"


def artifact_reference(path: Path, *, relative_to: Path) -> ArtifactReferenceV1:
    return ArtifactReferenceV1(
        path=path.resolve().relative_to(relative_to.resolve()).as_posix(),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
