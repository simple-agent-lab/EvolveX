from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from .candidate_snapshot import build_candidate_snapshot
from .surface import surface_patterns

SmokeMode = Literal["quick", "container", "full"]


@dataclass(frozen=True)
class CandidateSmokeResult:
    status: str
    mode: SmokeMode
    attempt_dir: Path
    dependency_digest: str


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
    include, exclude = surface_patterns(workspace)
    digest = build_candidate_snapshot(checkout, "HEAD", include=include, exclude=exclude).tree
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
        "dependency_digest": digest,
    }
    _write_json(attempt / "result.json", payload)
    if mode != "quick" and payload["status"] == "passed":
        _record_materialization(workspace, attempt, payload)
    return CandidateSmokeResult(str(payload["status"]), mode, attempt, digest)


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
