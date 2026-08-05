from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from ..runtime import OwnedResult, run_owned
from .models import ResolvedExecutionRuntime

CheckStatus = Literal["pass", "warn", "fail"]
ProbeRunner = Callable[..., OwnedResult]


@dataclass(frozen=True)
class RuntimeCheck:
    name: str
    status: CheckStatus
    detail: str
    remediation: str | None = None


@dataclass(frozen=True)
class ExecutionRuntimeProbeReport:
    receipt: dict[str, object]
    checks: tuple[RuntimeCheck, ...]
    docker_server_version: str | None = None
    docker_server_arch: str | None = None
    docker_root_dir: str | None = None
    compose_version: str | None = None
    workspace_free_bytes: int | None = None
    workspace_mount_verified: bool | None = None

    @property
    def healthy(self) -> bool:
        return all(check.status != "fail" for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "receipt": self.receipt,
            "checks": [asdict(check) for check in self.checks],
            "docker_server_version": self.docker_server_version,
            "docker_server_arch": self.docker_server_arch,
            "docker_root_dir": self.docker_root_dir,
            "compose_version": self.compose_version,
            "workspace_free_bytes": self.workspace_free_bytes,
            "workspace_mount_verified": self.workspace_mount_verified,
            "healthy": self.healthy,
        }


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_s: float = 30,
) -> OwnedResult:
    return run_owned(command, cwd=cwd, env=env, timeout_s=timeout_s)


def _docker_info(result: OwnedResult) -> tuple[str | None, str | None, str | None]:
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return None, None, None
    if not isinstance(payload, dict):
        return None, None, None
    return (
        str(payload.get("ServerVersion")) if payload.get("ServerVersion") else None,
        str(payload.get("Architecture")) if payload.get("Architecture") else None,
        str(payload.get("DockerRootDir")) if payload.get("DockerRootDir") else None,
    )


def probe_execution_runtime(
    runtime: ResolvedExecutionRuntime,
    *,
    workspace: Path,
    runner: ProbeRunner = _run,
    mount_image: str = "alpine:3.20",
    minimum_free_bytes: int | None = None,
) -> ExecutionRuntimeProbeReport:
    """Probe connectivity and host-path semantics without changing the workspace."""

    receipt = {**runtime.receipt.to_dict(), "fingerprint": runtime.receipt.fingerprint}
    required_free_bytes = (
        runtime.config.minimum_free_gib * 1024**3 if minimum_free_bytes is None else minimum_free_bytes
    )
    workspace_free = shutil.disk_usage(workspace).free
    workspace_check = RuntimeCheck(
        "workspace_disk",
        "pass" if workspace_free >= required_free_bytes else "fail",
        f"{workspace_free / 1024**3:.1f} GiB free for runs under {workspace}",
        None
        if workspace_free >= required_free_bytes
        else f"free or provision at least {runtime.config.minimum_free_gib} GiB for experiment artifacts",
    )
    if runtime.config.backend == "local":
        return ExecutionRuntimeProbeReport(
            receipt=receipt,
            checks=(
                RuntimeCheck("local_backend", "pass", "commands run in the current process namespace"),
                RuntimeCheck("isolation", "warn", "local backend provides no isolation or resource enforcement"),
                workspace_check,
            ),
            workspace_free_bytes=workspace_free,
        )

    environment = runtime.process_environment(os.environ)
    info = runner(
        ["docker", "info", "--format", "{{json .}}"],
        cwd=workspace,
        env=environment,
        timeout_s=30,
    )
    if info.returncode != 0:
        detail = (info.stderr or info.stdout or "docker info failed").strip()[-1000:]
        return ExecutionRuntimeProbeReport(
            receipt=receipt,
            checks=(
                RuntimeCheck(
                    "docker_daemon",
                    "fail",
                    detail,
                    "start Docker or select a reachable DOCKER_HOST/DOCKER_CONTEXT",
                ),
                workspace_check,
            ),
            workspace_free_bytes=workspace_free,
        )
    server_version, server_arch, docker_root = _docker_info(info)
    checks: list[RuntimeCheck] = [
        RuntimeCheck("docker_daemon", "pass", f"server={server_version or 'unknown'} arch={server_arch or 'unknown'}"),
        workspace_check,
    ]

    compose = runner(
        [*runtime.config.compose_command, "version", "--short"],
        cwd=workspace,
        env=environment,
        timeout_s=30,
    )
    compose_version = compose.stdout.strip() if compose.returncode == 0 else None
    checks.append(
        RuntimeCheck(
            "docker_compose",
            "pass" if compose.returncode == 0 else "fail",
            compose_version or (compose.stderr or compose.stdout or "Docker Compose is unavailable").strip()[-1000:],
            None
            if compose.returncode == 0
            else "install the Docker Compose v2 plugin and verify `docker compose version`",
        )
    )

    if docker_root and Path(docker_root).is_dir():
        free = shutil.disk_usage(docker_root).free
        checks.append(
            RuntimeCheck(
                "docker_disk",
                "pass" if free >= required_free_bytes else "fail",
                f"{free / 1024**3:.1f} GiB free at {docker_root}",
                None if free >= required_free_bytes else "free Docker storage or expand the Docker data volume",
            )
        )
    else:
        checks.append(
            RuntimeCheck(
                "docker_disk",
                "warn",
                "DockerRootDir is remote or not visible from the client host",
                "check free space on the Docker daemon host",
            )
        )

    mount_verified = False
    with tempfile.TemporaryDirectory(prefix="evolve-runtime-probe-", dir=workspace.parent) as temporary:
        probe_root = Path(temporary)
        marker = "evolve-mount-ok"
        mounted = runner(
            [
                "docker",
                "run",
                "--rm",
                "--mount",
                f"type=bind,source={probe_root},target=/evolve-probe",
                mount_image,
                "sh",
                "-c",
                f"printf %s {marker} > /evolve-probe/marker",
            ],
            cwd=workspace,
            env=environment,
            timeout_s=120,
        )
        marker_path = probe_root / "marker"
        mount_verified = mounted.returncode == 0 and marker_path.is_file() and marker_path.read_text() == marker
        checks.append(
            RuntimeCheck(
                "workspace_mount",
                "pass" if mount_verified else "fail",
                "daemon and host observe the same bind-mounted path"
                if mount_verified
                else (mounted.stderr or mounted.stdout or "bind mount marker did not return to the host").strip()[
                    -1000:
                ],
                None if mount_verified else "use a path shared with the Docker daemon or run Evolve on the daemon host",
            )
        )

    return ExecutionRuntimeProbeReport(
        receipt=receipt,
        checks=tuple(checks),
        docker_server_version=server_version,
        docker_server_arch=server_arch,
        docker_root_dir=docker_root,
        compose_version=compose_version,
        workspace_free_bytes=workspace_free,
        workspace_mount_verified=mount_verified,
    )
