from __future__ import annotations

import re
from pathlib import Path

_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")


def attempt_dir(
    workspace: Path,
    *,
    purpose: str,
    generation: str,
    candidate_commit: str,
    attempt: int,
) -> Path:
    path = _attempt_path(workspace, purpose, generation, candidate_commit, attempt)
    if path.exists():
        raise FileExistsError(f"evaluation attempt already exists: {path}")
    return path


def _attempt_path(
    workspace: Path, purpose: str, generation: str, candidate_commit: str, attempt: int
) -> Path:
    if attempt < 1:
        raise ValueError("attempt must be positive")
    for label, value in (
        ("purpose", purpose),
        ("generation", generation),
        ("candidate", candidate_commit),
    ):
        if not _SAFE_COMPONENT.fullmatch(value) or value in {".", ".."}:
            raise ValueError(f"unsafe {label} identity: {value!r}")
    path = (
        workspace
        / "runs"
        / "evaluations"
        / purpose
        / f"gen-{generation}"
        / f"candidate-{candidate_commit}"
        / f"attempt-{attempt}"
    )
    return path


def next_attempt(
    workspace: Path, *, purpose: str, generation: str, candidate_commit: str
) -> int:
    first = _attempt_path(workspace, purpose, generation, candidate_commit, 1)
    parent = first.parent
    attempts = [
        int(path.name.removeprefix("attempt-"))
        for path in parent.glob("attempt-*")
        if path.name.removeprefix("attempt-").isdigit()
    ] if parent.exists() else []
    return max(attempts, default=0) + 1
