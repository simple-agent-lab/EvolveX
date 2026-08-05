from __future__ import annotations

import os
import platform
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from .models import ExecutionRuntimeConfig, ResolvedExecutionRuntime


def _is_socket(path: Path) -> bool:
    try:
        return path.is_socket()
    except OSError:
        return False


def _endpoint_kind(value: str) -> str:
    scheme, separator, _ = value.partition("://")
    return scheme.lower() if separator and scheme else "custom"


def _uid() -> int | None:
    getter = getattr(os, "getuid", None)
    return getter() if getter is not None else None


def _socket_candidates(
    *,
    host_platform: str,
    home: Path,
    environment: Mapping[str, str],
    uid: int | None,
) -> tuple[tuple[Path, str], ...]:
    if host_platform.startswith("linux"):
        candidates: list[tuple[Path, str]] = [(Path("/var/run/docker.sock"), "linux-system")]
        runtime_dir = environment.get("XDG_RUNTIME_DIR")
        if runtime_dir:
            candidates.append((Path(runtime_dir) / "docker.sock", "linux-rootless"))
        elif uid is not None:
            candidates.append((Path("/run/user") / str(uid) / "docker.sock", "linux-rootless"))
        return tuple(candidates)
    if host_platform == "darwin":
        return (
            (home / ".colima" / "default" / "docker.sock", "colima"),
            (home / ".docker" / "run" / "docker.sock", "docker-desktop"),
        )
    return ()


def resolve_execution_runtime(
    config: ExecutionRuntimeConfig | None = None,
    environment: Mapping[str, str] | None = None,
    *,
    host_platform: str | None = None,
    host_arch: str | None = None,
    home: Path | None = None,
    uid: int | None = None,
    socket_probe: Callable[[Path], bool] = _is_socket,
) -> ResolvedExecutionRuntime:
    """Resolve one execution backend without probing or mutating the daemon.

    Explicit configuration and environment always win. Platform socket
    discovery is only a fallback; doctor-level connectivity, Compose, disk,
    and mount round-trip probes belong on top of this resolved context.
    """

    selected = config or ExecutionRuntimeConfig()
    values = dict(os.environ if environment is None else environment)
    resolved_platform = host_platform or sys.platform
    resolved_arch = host_arch or platform.machine()
    resolved_home = (home or Path(values.get("HOME") or Path.home())).expanduser()
    resolved_uid = _uid() if uid is None else uid

    if selected.backend == "local":
        return ResolvedExecutionRuntime(selected, resolved_platform, resolved_arch)

    if selected.docker_host is not None:
        endpoint = selected.docker_host
        return ResolvedExecutionRuntime(
            selected,
            resolved_platform,
            resolved_arch,
            docker_host=endpoint,
            endpoint_kind=_endpoint_kind(endpoint),
            endpoint_source="config",
        )

    environment_host = values.get("DOCKER_HOST")
    if environment_host:
        return ResolvedExecutionRuntime(
            selected,
            resolved_platform,
            resolved_arch,
            docker_host=environment_host,
            endpoint_kind=_endpoint_kind(environment_host),
            endpoint_source="environment",
        )

    if values.get("DOCKER_CONTEXT"):
        return ResolvedExecutionRuntime(
            selected,
            resolved_platform,
            resolved_arch,
            endpoint_kind="context",
            endpoint_source="environment",
        )

    for path, source in _socket_candidates(
        host_platform=resolved_platform,
        home=resolved_home,
        environment=values,
        uid=resolved_uid,
    ):
        if socket_probe(path):
            return ResolvedExecutionRuntime(
                selected,
                resolved_platform,
                resolved_arch,
                docker_host=f"unix://{path}",
                endpoint_kind="unix",
                endpoint_source=source,
            )

    return ResolvedExecutionRuntime(
        selected,
        resolved_platform,
        resolved_arch,
        endpoint_kind="context",
        endpoint_source="docker-cli-default",
    )
