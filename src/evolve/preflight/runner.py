from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path

from ..candidate.smoke import SmokeMode, SmokeResult, run_candidate_smoke
from ..evaluation.contract import (
    ContractResolutionContext,
    EvaluationContractResolutionError,
    resolve_evaluation_contract,
    trusted_evaluator_config,
)
from ..runtime import reserve_attempt_directory
from ..runtime.config import ResolvedRuntimeV1, RuntimeConfigError
from ..runtime.environment import (
    RuntimeEnvironmentErrorCode,
    RuntimeEnvironmentResolutionError,
    resolve_runtime_environment,
)
from . import checks as host_checks
from .models import (
    ArtifactReferenceV1,
    PreflightCheckStatus,
    PreflightCheckV1,
    PreflightFailureCategory,
    PreflightMode,
    PreflightResultV1,
    PreflightStatus,
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
    destination = receipt_path or next_receipt_path(root)
    completed: list[PreflightCheckV1] = []
    runtime: ResolvedRuntimeV1 | None = None

    try:
        evaluator = trusted_evaluator_config(root)
    except (EvaluationContractResolutionError, ValueError) as error:
        return _failed_result(
            mode,
            destination,
            completed,
            "configuration",
            PreflightFailureCategory.CONFIGURATION_INVALID,
            str(error),
            source_environment,
        )
    completed.append(_passed_check("configuration"))

    try:
        runtime = host_checks.trusted_runtime(root)
    except RuntimeConfigError as error:
        return _failed_result(
            mode,
            destination,
            completed,
            "runtime",
            PreflightFailureCategory.RUNTIME_INVALID,
            str(error),
            source_environment,
        )
    completed.append(_passed_check("runtime"))

    pinned_runtime = host_checks.git_text(root, "gen/0:evaluator/runtime.pin")
    if not pinned_runtime or pinned_runtime.strip() != runtime.digest:
        return _failed_result(
            mode,
            destination,
            completed,
            "runtime_digest",
            PreflightFailureCategory.RUNTIME_UNAVAILABLE,
            "runtime.pin does not match the resolved runtime",
            source_environment,
            runtime,
        )
    completed.append(_passed_check("runtime_digest"))

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
            completed,
            "evaluation_contract",
            PreflightFailureCategory.CONFIGURATION_INVALID,
            str(error),
            source_environment,
            runtime,
        )
    completed.append(_passed_check("evaluation_contract"))

    tools = ["docker", "harbor"] if runtime.engine == "harbor" else []
    if runtime.config.candidate is not None:
        tools.append(runtime.config.candidate.variant)
    for tool in tools:
        if not host_checks.tool_available(tool, source_environment):
            return _failed_result(
                mode,
                destination,
                completed,
                "dependency_tools",
                PreflightFailureCategory.DEPENDENCY_TOOL_UNAVAILABLE,
                f"required dependency tool is unavailable: {tool}",
                source_environment,
                runtime,
            )
    completed.append(_passed_check("dependency_tools"))

    candidate_runtime = runtime.config.candidate
    if candidate_runtime is not None:
        project = candidate_root / candidate_runtime.project
        if not host_checks.lock_valid(project, source_environment):
            return _failed_result(
                mode,
                destination,
                completed,
                "dependency_lock",
                PreflightFailureCategory.DEPENDENCY_LOCK_INVALID,
                "candidate uv lock validation failed",
                source_environment,
                runtime,
            )
        completed.append(_passed_check("dependency_lock"))

    try:
        resolve_runtime_environment(
            runtime,
            source_environment,
            agent_kind=str(evaluator.get("agent") or ""),
        )
    except RuntimeEnvironmentResolutionError as error:
        return _failed_result(
            mode,
            destination,
            completed,
            "runtime_environment",
            _environment_failure_category(error),
            str(error),
            source_environment,
            runtime,
        )
    completed.append(_passed_check("runtime_environment"))

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
                completed,
                "model_agent_request",
                PreflightFailureCategory.MODEL_SMOKE_FAILED,
                str(error) or type(error).__name__,
                source_environment,
                runtime,
            )
        smoke_artifact = host_checks.artifact_reference(smoke.attempt_dir / "result.json", relative_to=root)
        if smoke.status != "passed":
            return _failed_result(
                mode,
                destination,
                completed,
                "model_agent_request",
                _structured_smoke_failure_category(smoke) or PreflightFailureCategory.MODEL_SMOKE_FAILED,
                _smoke_failure_message(smoke),
                source_environment,
                runtime,
                artifact=smoke_artifact,
            )
        completed.append(
            PreflightCheckV1(
                name="model_agent_request",
                status=PreflightCheckStatus.PASSED,
                artifact=smoke_artifact,
            )
        )

    result = PreflightResultV1(
        schema_version=1,
        status=PreflightStatus.PASSED,
        runtime_digest=runtime.digest,
        endpoint_digest=runtime.endpoint_digest,
        mode=mode,
        checks=tuple(completed),
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
    runtime: ResolvedRuntimeV1 | None = None,
    *,
    artifact: ArtifactReferenceV1 | None = None,
) -> PreflightResultV1:
    bounded = _bounded_message(message, environment)
    result = PreflightResultV1.failed(
        mode=mode,
        runtime_digest=runtime.digest if runtime is not None else "",
        endpoint_digest=runtime.endpoint_digest if runtime is not None else "",
        checks=(
            *completed,
            PreflightCheckV1(
                name=check_name,
                status=PreflightCheckStatus.FAILED,
                failure_category=category,
                message=bounded,
                artifact=artifact,
            ),
        ),
        category=category,
        message=bounded,
        receipt_path=destination,
    )
    result.write()
    return result


def _passed_check(name: str) -> PreflightCheckV1:
    return PreflightCheckV1(name=name, status=PreflightCheckStatus.PASSED)


def _environment_failure_category(
    error: RuntimeEnvironmentResolutionError,
) -> PreflightFailureCategory:
    categories = {
        RuntimeEnvironmentErrorCode.CREDENTIAL_FORBIDDEN: PreflightFailureCategory.CREDENTIAL_FORBIDDEN,
        RuntimeEnvironmentErrorCode.CREDENTIAL_MISSING: PreflightFailureCategory.CREDENTIAL_MISSING,
        RuntimeEnvironmentErrorCode.AUTH_JSON_MISSING: PreflightFailureCategory.AUTH_JSON_MISSING,
        RuntimeEnvironmentErrorCode.AUTH_JSON_UNSUPPORTED: PreflightFailureCategory.AUTH_JSON_UNSUPPORTED,
        RuntimeEnvironmentErrorCode.ENDPOINT_INVALID: PreflightFailureCategory.ENDPOINT_INVALID,
    }
    return categories.get(error.code, PreflightFailureCategory.CONFIGURATION_INVALID)


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


def _bounded_message(message: str, environment: Mapping[str, str]) -> str:
    redacted = message
    values = {
        value for name, value in environment.items() if _SENSITIVE_ENVIRONMENT_NAME.search(name) and len(value) >= 4
    }
    for value in sorted(values, key=len, reverse=True):
        redacted = redacted.replace(value, "[REDACTED]")
    redacted = re.sub(r"(?i)https?://[^\s]+", "[REDACTED_URL]", redacted)
    return redacted[:500]


def next_receipt_path(workspace: Path) -> Path:
    return reserve_attempt_directory(workspace / "runs" / "preflight") / "preflight.json"
