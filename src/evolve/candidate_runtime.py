from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


class CandidateDependencyError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CandidateDependencyIdentity:
    project_sha256: str
    lock_sha256: str

    @property
    def digest(self) -> str:
        payload = f"{self.project_sha256}\n{self.lock_sha256}\n".encode()
        return hashlib.sha256(payload).hexdigest()


def validate_miniswe_candidate(
    checkout: Path,
    *,
    changed_paths: Iterable[str] = (),
) -> CandidateDependencyIdentity:
    target = checkout / "target"
    project = target / "pyproject.toml"
    lock = target / "uv.lock"
    changed = set(changed_paths)
    if not project.is_file():
        raise CandidateDependencyError("project_missing", "target/pyproject.toml is required")
    if not lock.is_file():
        raise CandidateDependencyError("lock_missing", "target/uv.lock is required")
    if "target/pyproject.toml" in changed and "target/uv.lock" not in changed:
        raise CandidateDependencyError(
            "project_changed_without_lock",
            "target/pyproject.toml changed without target/uv.lock",
        )
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/tmp/evolve-candidate-runtime-uv")
    result = subprocess.run(
        ["uv", "lock", "--check", "--offline", "--python", sys.executable, "--project", str(target)],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if result.returncode:
        raise CandidateDependencyError(
            "lock_incompatible",
            "target/uv.lock does not match target/pyproject.toml",
        )
    return CandidateDependencyIdentity(_sha256(project), _sha256(lock))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
