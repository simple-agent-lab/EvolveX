from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal

ExecutionBackend = Literal["local", "docker"]


@dataclass(frozen=True)
class ExecutionRuntimeConfig:
    """Declared host backend configuration.

    This is separate from ``CandidateRuntimeResult``: the latter describes
    dependencies mounted into a benchmark candidate, while this object
    describes how the host reaches the environment that executes it.
    """

    backend: ExecutionBackend = "docker"
    docker_host: str | None = None
    compose_command: tuple[str, ...] = ("docker", "compose")
    minimum_free_gib: int = 20

    def __post_init__(self) -> None:
        if self.backend not in {"local", "docker"}:
            raise ValueError(f"unsupported execution runtime backend: {self.backend!r}")
        if self.docker_host is not None and not self.docker_host.strip():
            raise ValueError("execution runtime docker_host must be non-empty")
        if not self.compose_command or any(not value for value in self.compose_command):
            raise ValueError("execution runtime compose_command must contain non-empty arguments")
        if (
            isinstance(self.minimum_free_gib, bool)
            or not isinstance(self.minimum_free_gib, int)
            or self.minimum_free_gib < 1
        ):
            raise ValueError("execution runtime minimum_free_gib must be a positive integer")


@dataclass(frozen=True)
class ExecutionRuntimeReceipt:
    """Stable, non-secret runtime provenance suitable for persisted reports."""

    schema_version: int
    backend: ExecutionBackend
    host_platform: str
    host_arch: str
    endpoint_kind: str | None
    endpoint_source: str | None
    compose_command: tuple[str, ...] | None
    minimum_free_gib: int

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        if self.compose_command is not None:
            payload["compose_command"] = list(self.compose_command)
        return payload

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ResolvedExecutionRuntime:
    """Machine-local execution details plus a stable redacted receipt."""

    config: ExecutionRuntimeConfig
    host_platform: str
    host_arch: str
    docker_host: str | None = None
    endpoint_kind: str | None = None
    endpoint_source: str | None = None

    def process_environment(self, source: Mapping[str, str]) -> dict[str, str]:
        values = dict(source)
        if self.config.backend == "docker" and self.docker_host:
            values["DOCKER_HOST"] = self.docker_host
        return values

    @property
    def receipt(self) -> ExecutionRuntimeReceipt:
        return ExecutionRuntimeReceipt(
            schema_version=1,
            backend=self.config.backend,
            host_platform=self.host_platform,
            host_arch=self.host_arch,
            endpoint_kind=self.endpoint_kind,
            endpoint_source=self.endpoint_source,
            compose_command=self.config.compose_command if self.config.backend == "docker" else None,
            minimum_free_gib=self.config.minimum_free_gib,
        )
