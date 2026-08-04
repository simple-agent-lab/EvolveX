from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import ExecutionBackend, ExecutionRuntimeConfig


def execution_runtime_config(
    values: Mapping[str, Any] | None,
    *,
    default_backend: ExecutionBackend = "docker",
) -> ExecutionRuntimeConfig:
    """Validate the portable ``execution_runtime`` config section."""

    configured = {} if values is None else dict(values)
    backend = configured.get("backend", default_backend)
    if not isinstance(backend, str):
        raise ValueError("execution_runtime.backend must be local or docker")

    docker_host = configured.get("docker_host")
    if docker_host is not None and not isinstance(docker_host, str):
        raise ValueError("execution_runtime.docker_host must be a string")

    compose = configured.get("compose_command", ["docker", "compose"])
    if not isinstance(compose, list) or any(not isinstance(value, str) or not value for value in compose):
        raise ValueError("execution_runtime.compose_command must be a list of non-empty strings")
    minimum_free_gib = configured.get("minimum_free_gib", 20)
    if isinstance(minimum_free_gib, bool) or not isinstance(minimum_free_gib, int):
        raise ValueError("execution_runtime.minimum_free_gib must be a positive integer")

    return ExecutionRuntimeConfig(
        backend=backend,  # type: ignore[arg-type]
        docker_host=docker_host,
        compose_command=tuple(compose),
        minimum_free_gib=minimum_free_gib,
    )
