from __future__ import annotations

import json
from pathlib import Path

import pytest

from evolve.execution_runtime import (
    ExecutionRuntimeConfig,
    execution_runtime_config,
    probe_execution_runtime,
    resolve_execution_runtime,
)
from evolve.runtime import OwnedResult


def _probe(*available: Path):
    resolved = {path.resolve() for path in available}
    return lambda path: path.resolve() in resolved


def test_local_runtime_does_not_inject_docker_environment(tmp_path: Path) -> None:
    runtime = resolve_execution_runtime(
        ExecutionRuntimeConfig(backend="local"),
        {"HOME": str(tmp_path), "DOCKER_HOST": "unix:///ignored.sock"},
        host_platform="linux",
        host_arch="x86_64",
    )

    assert runtime.docker_host is None
    assert runtime.process_environment({"PATH": "/usr/bin"}) == {"PATH": "/usr/bin"}
    assert runtime.receipt.compose_command is None


def test_explicit_config_docker_host_wins_over_environment() -> None:
    runtime = resolve_execution_runtime(
        ExecutionRuntimeConfig(docker_host="ssh://builder.example"),
        {"DOCKER_HOST": "unix:///environment.sock"},
        host_platform="linux",
        host_arch="x86_64",
    )

    assert runtime.docker_host == "ssh://builder.example"
    assert runtime.endpoint_kind == "ssh"
    assert runtime.endpoint_source == "config"
    assert runtime.process_environment({"DOCKER_HOST": "unix:///environment.sock"})["DOCKER_HOST"] == (
        "ssh://builder.example"
    )


def test_environment_docker_host_wins_over_platform_sockets(tmp_path: Path) -> None:
    runtime = resolve_execution_runtime(
        environment={"HOME": str(tmp_path), "DOCKER_HOST": "tcp://docker.example:2376"},
        host_platform="darwin",
        host_arch="arm64",
        socket_probe=lambda _path: True,
    )

    assert runtime.docker_host == "tcp://docker.example:2376"
    assert runtime.endpoint_kind == "tcp"
    assert runtime.endpoint_source == "environment"


def test_linux_system_socket_precedes_rootless_socket(tmp_path: Path) -> None:
    system = Path("/var/run/docker.sock")
    rootless = tmp_path / "docker.sock"
    runtime = resolve_execution_runtime(
        environment={"HOME": str(tmp_path), "XDG_RUNTIME_DIR": str(tmp_path)},
        host_platform="linux",
        host_arch="x86_64",
        socket_probe=_probe(system, rootless),
    )

    assert runtime.docker_host == "unix:///var/run/docker.sock"
    assert runtime.endpoint_source == "linux-system"


def test_linux_rootless_socket_is_discovered(tmp_path: Path) -> None:
    rootless = tmp_path / "docker.sock"
    runtime = resolve_execution_runtime(
        environment={"HOME": str(tmp_path), "XDG_RUNTIME_DIR": str(tmp_path)},
        host_platform="linux",
        host_arch="x86_64",
        socket_probe=_probe(rootless),
    )

    assert runtime.docker_host == f"unix://{rootless}"
    assert runtime.endpoint_source == "linux-rootless"


def test_colima_socket_is_discovered_on_macos(tmp_path: Path) -> None:
    colima = tmp_path / ".colima" / "default" / "docker.sock"
    runtime = resolve_execution_runtime(
        environment={"HOME": str(tmp_path)},
        host_platform="darwin",
        host_arch="arm64",
        socket_probe=_probe(colima),
    )

    assert runtime.docker_host == f"unix://{colima}"
    assert runtime.endpoint_source == "colima"


def test_docker_context_environment_defers_to_cli_context(tmp_path: Path) -> None:
    runtime = resolve_execution_runtime(
        environment={"HOME": str(tmp_path), "DOCKER_CONTEXT": "remote-builder"},
        host_platform="linux",
        host_arch="x86_64",
        socket_probe=lambda _path: True,
    )

    assert runtime.docker_host is None
    assert runtime.endpoint_kind == "context"
    assert runtime.endpoint_source == "environment"


def test_receipt_is_stable_and_does_not_persist_endpoint_value() -> None:
    runtime = resolve_execution_runtime(
        environment={"DOCKER_HOST": "tcp://user:secret@docker.example:2376"},
        host_platform="linux",
        host_arch="x86_64",
    )
    receipt = runtime.receipt

    assert "docker.example" not in str(receipt.to_dict())
    assert len(receipt.fingerprint) == 64


@pytest.mark.parametrize("backend", ["podman", "", "Docker"])
def test_execution_runtime_rejects_unknown_backend(backend: str) -> None:
    with pytest.raises(ValueError, match="unsupported execution runtime backend"):
        ExecutionRuntimeConfig(backend=backend)  # type: ignore[arg-type]


def test_execution_runtime_config_validates_portable_section() -> None:
    config = execution_runtime_config(
        {
            "backend": "docker",
            "docker_host": "ssh://builder.example",
            "compose_command": ["docker", "compose"],
            "minimum_free_gib": 80,
        }
    )

    assert config.docker_host == "ssh://builder.example"
    assert config.minimum_free_gib == 80


def test_docker_probe_checks_daemon_compose_disk_and_bind_mount(tmp_path: Path) -> None:
    runtime = resolve_execution_runtime(
        ExecutionRuntimeConfig(docker_host="unix:///runtime.sock", minimum_free_gib=1),
        host_platform="linux",
        host_arch="x86_64",
    )
    environments: list[dict[str, str]] = []

    def runner(command, *, cwd, env, timeout_s):
        environments.append(env)
        if command[:2] == ["docker", "info"]:
            return OwnedResult(
                0,
                json.dumps({"ServerVersion": "27.0", "Architecture": "x86_64", "DockerRootDir": str(tmp_path)}),
                "",
                0.0,
                False,
            )
        if command[:3] == ["docker", "compose", "version"]:
            return OwnedResult(0, "v2.30.0\n", "", 0.0, False)
        mount = command[command.index("--mount") + 1]
        source = Path(dict(item.split("=", 1) for item in mount.split(","))["source"])
        (source / "marker").write_text("evolve-mount-ok")
        return OwnedResult(0, "", "", 0.0, False)

    report = probe_execution_runtime(runtime, workspace=tmp_path, runner=runner, minimum_free_bytes=0)

    assert report.healthy
    assert report.workspace_mount_verified is True
    assert {check.name for check in report.checks} >= {
        "docker_daemon",
        "docker_compose",
        "docker_disk",
        "workspace_disk",
        "workspace_mount",
    }
    assert all(env["DOCKER_HOST"] == "unix:///runtime.sock" for env in environments)
