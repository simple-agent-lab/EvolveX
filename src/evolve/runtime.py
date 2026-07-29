from __future__ import annotations

import hashlib
import os
import re
import signal
import subprocess
import time
from collections.abc import Iterable
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
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_s: float | None = None,
) -> OwnedResult:
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
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
    targets = _process_tree(process.pid)
    _signal_process_tree(targets, signal.SIGTERM, fallback_group=process.pid)
    try:
        output = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        _signal_process_tree(
            _process_tree(process.pid) | targets,
            signal.SIGKILL,
            fallback_group=process.pid,
        )
        return process.communicate()
    descendants = targets - {process.pid}
    _wait_for_process_tree(descendants, timeout_s=5)
    # ``communicate`` reaped the root process. Never probe its PID again here:
    # the operating system may already have reused it for an unrelated process.
    _signal_process_tree(_alive_pids(descendants), signal.SIGKILL)
    return output


def _process_tree(root_pid: int) -> set[int]:
    """Snapshot a process and all descendants, including children in new sessions."""
    children: dict[int, list[int]] = {}
    proc = Path("/proc")
    try:
        entries = list(proc.iterdir())
    except OSError:
        return {root_pid}
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text()
            parent_line = next(line for line in status.splitlines() if line.startswith("PPid:"))
            parent = int(parent_line.split()[1])
        except (OSError, StopIteration, ValueError):
            continue
        children.setdefault(parent, []).append(int(entry.name))
    result = {root_pid}
    pending = [root_pid]
    while pending:
        child_pids = children.get(pending.pop(), ())
        for child_pid in child_pids:
            if child_pid not in result:
                result.add(child_pid)
                pending.append(child_pid)
    return result


def _alive_pids(pids: Iterable[int]) -> set[int]:
    alive: set[int] = set()
    for pid in pids:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            continue
        alive.add(pid)
    return alive


def _wait_for_process_tree(pids: Iterable[int], *, timeout_s: float) -> None:
    pending = set(pids)
    deadline = time.monotonic() + timeout_s
    while pending and time.monotonic() < deadline:
        pending = _alive_pids(pending)
        if pending:
            time.sleep(0.05)


def _signal_process_tree(
    pids: Iterable[int],
    sig: signal.Signals,
    *,
    fallback_group: int | None = None,
) -> None:
    """Signal every process group represented in a captured descendant tree."""
    process_ids = set(pids)
    groups: set[int] = set()
    own_group = os.getpgrp()
    if fallback_group is not None:
        # ``run_owned`` starts its root process in a new session, so its PID is
        # already the authoritative process-group ID. Do not resolve it again:
        # the process may have exited (and its PID may have been reused) between
        # the process-tree snapshot and cleanup.
        process_ids.discard(fallback_group)
    if fallback_group is not None and fallback_group > 0 and fallback_group != own_group:
        groups.add(fallback_group)
    for pid in process_ids:
        try:
            group = os.getpgid(pid)
        except (ProcessLookupError, PermissionError):
            continue
        if group > 0 and group != own_group:
            groups.add(group)
    for group in groups:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(group, sig)


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
    attempts = (
        [int(path.name[8:]) for path in parent.glob("attempt-*") if path.name[8:].isdigit()] if parent.exists() else []
    )
    return max(attempts, default=0) + 1
