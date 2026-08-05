from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


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
    PROFILE_NOT_FOUND = "profile_not_found"
    PROFILE_AMBIGUOUS = "profile_ambiguous"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    RUNTIME_IMAGE_UNAVAILABLE = "runtime_image_unavailable"
    DEPENDENCY_LOCK_INVALID = "dependency_lock_invalid"
    DEPENDENCY_TOOL_UNAVAILABLE = "dependency_tool_unavailable"
    CREDENTIAL_MISSING = "credential_missing"
    CREDENTIAL_FORBIDDEN = "credential_forbidden"
    AUTH_JSON_MISSING = "auth_json_missing"
    AUTH_JSON_UNSUPPORTED = "auth_json_unsupported"
    ENDPOINT_INVALID = "endpoint_invalid"
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
    endpoint_digest: str
    mode: PreflightMode
    checks: tuple[PreflightCheckV1, ...]
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
            "endpoint_digest": self.endpoint_digest,
            "mode": self.mode.value,
            "checks": [check.to_dict() for check in self.checks],
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
        endpoint_digest: str,
        checks: tuple[PreflightCheckV1, ...],
        category: PreflightFailureCategory,
        message: str,
        receipt_path: Path | None = None,
    ) -> PreflightResultV1:
        return cls(
            schema_version=1,
            status=PreflightStatus.FAILED,
            profile_name=profile_name,
            profile_digest=profile_digest,
            runtime_digest=runtime_digest,
            endpoint_digest=endpoint_digest,
            mode=mode,
            checks=checks,
            failure_category=category,
            failure_message=message,
            receipt_path=receipt_path,
        )
