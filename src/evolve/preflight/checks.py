from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from ..git import git
from ..host_runtime import uv_executable
from ..runtime.config import ResolvedRuntimeV1, RuntimeConfigError, load_resolved_runtime
from .models import ArtifactReferenceV1


def trusted_runtime(workspace: Path) -> ResolvedRuntimeV1:
    text = git_text(workspace, "gen/0:evaluator/runtime.json")
    if text is None:
        raise RuntimeConfigError("gen/0 runtime.json is unavailable")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeConfigError("gen/0 runtime.json is invalid JSON") from error
    return load_resolved_runtime(payload)


def git_text(workspace: Path, revision: str) -> str | None:
    result = git(workspace, "show", revision, check=False)
    return result.stdout if result.returncode == 0 else None


def tool_available(name: str, environment: Mapping[str, str]) -> bool:
    return shutil.which(name, path=environment.get("PATH")) is not None


def lock_valid(project: Path, environment: Mapping[str, str]) -> bool:
    if not (project / "pyproject.toml").is_file() or not (project / "uv.lock").is_file():
        return False
    try:
        uv = uv_executable(environment)
    except RuntimeError:
        return False
    return local_command_succeeds(
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


def local_command_succeeds(command: list[str], environment: Mapping[str, str]) -> bool:
    try:
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
            env=dict(environment),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def artifact_reference(path: Path, *, relative_to: Path) -> ArtifactReferenceV1:
    return ArtifactReferenceV1(
        path=path.resolve().relative_to(relative_to.resolve()).as_posix(),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
