from __future__ import annotations

import os
import shlex
import shutil
from collections.abc import Mapping
from pathlib import Path

from .models import ResolvedExecutionRuntime


def prepare_execution_environment(
    runtime: ResolvedExecutionRuntime,
    source: Mapping[str, str],
    *,
    runtime_root: Path,
) -> dict[str, str]:
    """Return the host environment expected by Harbor.

    Harbor currently invokes Compose as ``docker compose`` internally.  When a
    host declares a different compatible command (for example the standalone
    ``docker-compose`` binary), put a small Docker CLI bridge first on PATH so
    Harbor observes the configured command too.  Non-Compose Docker commands
    continue to use the real Docker CLI.
    """

    environment = runtime.process_environment(source)
    if runtime.config.backend != "docker" or runtime.config.compose_command == ("docker", "compose"):
        return environment

    path = environment.get("PATH")
    docker = shutil.which("docker", path=path)
    if docker is None:
        raise RuntimeError("execution runtime requires the docker CLI on PATH")

    configured = runtime.config.compose_command
    compose = shutil.which(configured[0], path=path)
    if compose is None:
        raise RuntimeError(f"execution runtime compose command not found on PATH: {configured[0]}")

    bridge_dir = runtime_root.resolve() / "host-bin"
    bridge_dir.mkdir(parents=True, exist_ok=True)
    bridge = bridge_dir / "docker"
    compose_command = " ".join(shlex.quote(value) for value in (compose, *configured[1:]))
    docker_command = shlex.quote(docker)
    contents = (
        "#!/bin/sh\n"
        'if [ "${1-}" = "compose" ]; then\n'
        "  shift\n"
        f'  exec {compose_command} "$@"\n'
        "fi\n"
        f'exec {docker_command} "$@"\n'
    )
    temporary = bridge.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text(contents)
    temporary.chmod(0o755)
    temporary.replace(bridge)

    environment["PATH"] = f"{bridge_dir}{os.pathsep}{path or ''}"
    return environment
