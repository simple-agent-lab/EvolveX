from __future__ import annotations

import json
import os
import re
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .candidate_snapshot import build_candidate_snapshot, materialize_snapshot
from .runtime import owned_attempt_id, run_owned
from .surface import surface_patterns

SmokeStatus = Literal["passed", "failed", "unsupported"]
_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PROXY", re.IGNORECASE)
_URL_USERINFO = re.compile(r"(?i)(https?://)[^/@\s]+@")
_COMMON_SECRET_VALUES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(?:gh[opusr]|github_pat)_[A-Za-z0-9_]{16,}\b"),
)
_COMMON_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+"
)


@dataclass(frozen=True)
class SmokeResult:
    status: SmokeStatus
    attempt_dir: Path
    snapshot_tree: str
    returncode: int | None
    stdout_path: Path
    stderr_path: Path


def run_candidate_smoke(checkout: Path, *, workspace: Path) -> SmokeResult:
    include, exclude = surface_patterns(workspace)
    snapshot = build_candidate_snapshot(checkout, "HEAD", include=include, exclude=exclude)
    attempt = _next_attempt(workspace / "runs" / "smoke")
    started = time.monotonic()
    with materialize_snapshot(checkout, snapshot) as materialized:
        script = materialized / "evaluator" / "smoke.sh"
        if not script.is_file():
            return _write_result(attempt, "unsupported", snapshot.tree, None, "", "", time.monotonic() - started)
        env = {**os.environ, "EVOLVE_RUN_DIR": str(attempt), "EVOLVE_ATTEMPT_ID": owned_attempt_id(workspace, attempt)}
        env.setdefault("EVOLVE_FRAMEWORK_PYTHON", sys.executable)
        completed = run_owned([str(script)], cwd=materialized, env=env)
    return _write_result(
        attempt,
        "passed" if completed.returncode == 0 else "failed",
        snapshot.tree,
        completed.returncode,
        _redact(completed.stdout, os.environ),
        _redact(completed.stderr, os.environ),
        time.monotonic() - started,
    )


def _next_attempt(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    number = 1
    while True:
        attempt = root / f"attempt-{number}"
        try:
            attempt.mkdir()
        except FileExistsError:
            number += 1
            continue
        return attempt


def _redact(text: str, environment: Mapping[str, str]) -> str:
    redacted = _URL_USERINFO.sub(r"\1[REDACTED]@", text)
    values = {
        value
        for name, value in environment.items()
        if len(value) >= 4 and _SECRET_NAME.search(name)
    }
    for value in sorted(values, key=len, reverse=True):
        redacted = redacted.replace(value, "[REDACTED]")
    for pattern in _COMMON_SECRET_VALUES:
        redacted = pattern.sub("[REDACTED]", redacted)
    redacted = _COMMON_SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", redacted)
    return redacted


def _write_result(
    attempt: Path,
    status: SmokeStatus,
    snapshot_tree: str,
    returncode: int | None,
    stdout: str,
    stderr: str,
    duration_s: float,
) -> SmokeResult:
    stdout_path = attempt / "stdout.log"
    stderr_path = attempt / "stderr.log"
    stdout_path.write_text(stdout)
    stderr_path.write_text(stderr)
    payload = {
        "schema_version": 1,
        "status": status,
        "snapshot_tree": snapshot_tree,
        "returncode": returncode,
        "duration_s": round(duration_s, 6),
        "stdout_path": str(stdout_path.resolve()),
        "stderr_path": str(stderr_path.resolve()),
    }
    (attempt / "result.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return SmokeResult(status, attempt, snapshot_tree, returncode, stdout_path, stderr_path)
