from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

SmokeMode = Literal["quick", "container", "full"]


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


@dataclass(frozen=True)
class CandidateSmokeResult:
    status: str
    mode: SmokeMode
    attempt_dir: Path
    dependency_digest: str


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


def select_smoke_mode(*, quick: bool, container: bool, full: bool) -> SmokeMode:
    selected = [name for name, enabled in (("quick", quick), ("container", container), ("full", full)) if enabled]
    if len(selected) > 1:
        raise ValueError("choose only one smoke mode")
    return cast("SmokeMode", selected[0] if selected else "full")


def run_candidate_smoke(
    checkout: Path,
    *,
    workspace: Path,
    run_dir: Path,
    mode: SmokeMode = "full",
) -> CandidateSmokeResult:
    if mode not in {"quick", "container", "full"}:
        raise ValueError(f"unknown smoke mode: {mode}")
    attempt = _next_attempt(run_dir / "meta_agent" / "smoke")
    started = time.monotonic()
    try:
        identity = validate_miniswe_candidate(checkout)
    except CandidateDependencyError as exc:
        payload: dict[str, object] = {
            "schema_version": 1,
            "mode": mode,
            "status": "candidate_invalid",
            "owner": "candidate",
            "category": exc.code,
            "duration_s": round(time.monotonic() - started, 6),
        }
        _write_json(attempt / "result.json", payload)
        return CandidateSmokeResult("candidate_invalid", mode, attempt, "")
    if mode == "quick":
        harbor = {"status": "passed", "owner": "none", "category": "none"}
    else:
        harbor = _run_harbor_smoke(checkout, workspace, attempt, mode)
    payload = {
        "schema_version": 1,
        "mode": mode,
        "status": str(harbor.get("status", "infrastructure_failed")),
        "owner": str(harbor.get("owner", "infrastructure")),
        "category": str(harbor.get("category", "setup_failed")),
        "duration_s": round(time.monotonic() - started, 6),
        "project_sha256": identity.project_sha256,
        "lock_sha256": identity.lock_sha256,
        "dependency_digest": identity.digest,
    }
    _write_json(attempt / "result.json", payload)
    if mode != "quick" and payload["status"] == "passed":
        _record_materialization(workspace, attempt, payload)
    return CandidateSmokeResult(str(payload["status"]), mode, attempt, identity.digest)


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


def _run_harbor_smoke(checkout: Path, workspace: Path, attempt: Path, mode: SmokeMode) -> dict[str, object]:
    cache = workspace / "runs" / "runtime" / "uv-cache"
    jobs = attempt / "jobs"
    cache.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "EVOLVE_RUN_DIR": str(attempt),
            "EVOLVE_CANDIDATE_SMOKE_MODE": mode,
            "EVOLVE_CANDIDATE_SMOKE_JOBS_DIR": str(jobs),
            "EVOLVE_TASK_LIMIT": "1",
            "EVOLVE_HARBOR_N": "1",
            "EVOLVE_HARBOR_ATTEMPTS": "1",
            "EVOLVE_HARBOR_N_CONCURRENT": "1",
            "EVOLVE_UV_CACHE_DIR": str(cache),
        }
    )
    env.setdefault("EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER", "6")
    completed = subprocess.run(
        [str(checkout / "evaluator" / "eval.sh")],
        cwd=checkout,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    result_path = attempt / "harbor-result.json"
    if result_path.is_file():
        try:
            result = json.loads(result_path.read_text())
        except json.JSONDecodeError:
            result = None
        if isinstance(result, dict):
            return result
    return {
        "status": "infrastructure_failed",
        "owner": "infrastructure",
        "category": "setup_failed" if completed.returncode else "missing_result",
    }


def _record_materialization(workspace: Path, attempt: Path, payload: dict[str, object]) -> None:
    digest = str(payload["dependency_digest"])
    record_dir = workspace / "runs" / "runtime" / "candidates" / digest / "attempts"
    _write_json(record_dir / f"{attempt.name}-{time.time_ns()}.json", payload)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)
