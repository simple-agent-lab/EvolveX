from __future__ import annotations

import hashlib
import os
import re
import signal
import subprocess
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")


@dataclass(frozen=True)
class OwnedResult:
    returncode: int
    stdout: str
    stderr: str
    wall_s: float
    timed_out: bool


def run_owned(
    command: list[str], *, cwd: Path, env: dict[str, str], timeout_s: float | None = None,
) -> OwnedResult:
    started = time.monotonic()
    process = subprocess.Popen(
        command, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        stdout, stderr = _terminate(process)
        timed_out = True
    except BaseException:
        _terminate(process)
        raise
    assert process.returncode is not None
    return OwnedResult(process.returncode, stdout, stderr, time.monotonic() - started, timed_out)


def _terminate(process: subprocess.Popen[str]) -> tuple[str, str]:
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        return process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        return process.communicate()


def owned_attempt_id(workspace: Path, run_dir: Path) -> str:
    relative = run_dir.resolve().relative_to(workspace.resolve()).as_posix()
    prefix = re.sub(r"[^a-z0-9_-]", "-", f"{workspace.name}-{relative}".lower()).strip("-")[:48]
    return f"{prefix}-{hashlib.sha256(str((workspace.resolve(), relative)).encode()).hexdigest()[:16]}"


def _attempt_parent(workspace: Path, purpose: str, generation: str, candidate_commit: str) -> Path:
    for label, value in (("purpose", purpose), ("generation", generation), ("candidate", candidate_commit)):
        if not _SAFE_COMPONENT.fullmatch(value) or value in {".", ".."}:
            raise ValueError(f"unsafe {label} identity: {value!r}")
    return workspace / "runs/evaluations" / purpose / f"gen-{generation}" / f"candidate-{candidate_commit}"


def attempt_dir(workspace: Path, *, purpose: str, generation: str, candidate_commit: str, attempt: int) -> Path:
    if attempt < 1:
        raise ValueError("attempt must be positive")
    if (path := _attempt_parent(workspace, purpose, generation, candidate_commit) / f"attempt-{attempt}").exists():
        raise FileExistsError(f"evaluation attempt already exists: {path}")
    return path


def next_attempt(workspace: Path, *, purpose: str, generation: str, candidate_commit: str) -> int:
    parent = _attempt_parent(workspace, purpose, generation, candidate_commit)
    attempts = [int(path.name[8:]) for path in parent.glob("attempt-*") if path.name[8:].isdigit()] if parent.exists() else []
    return max(attempts, default=0) + 1
