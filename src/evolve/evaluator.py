from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .config import load_config
from .git import evaluator_tree, git
from .task_sets import TaskSetIdentity, effective_task_set_identity
from .task_vectors import validate_task_vector


@dataclass(frozen=True)
class EvaluationResult:
    score: float | None
    status: str
    task_set_hash: str
    evaluator_tree: str
    wall_s: float
    task_vector: dict | None = None  # per-task pass/fail, when the evaluator emits it
    evaluation_artifacts: dict[str, str] | None = None
    task_set_members: tuple[str, ...] = ()


def evaluate(
    workspace: Path,
    tag: str,
    genid: str,
    *,
    round_number: int | None = None,
    run_name: str = "eval",
    task_limit: int | None = None,
    eval_kind: str = "research",
) -> EvaluationResult:
    start = time.monotonic()
    run_dir = workspace / "runs" / f"gen-{genid}" / run_name
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    tag_evaluator_tree = evaluator_tree(workspace, tag)
    baseline_tree = evaluator_tree(workspace, "gen/0")
    if tag_evaluator_tree != baseline_tree:
        raise RuntimeError(f"evaluator tree for {tag} differs from gen/0")

    with tempfile.TemporaryDirectory(prefix="evolve-eval-") as tempdir:
        checkout = Path(tempdir) / "checkout"
        git(workspace, "worktree", "add", "--detach", str(checkout), tag)
        try:
            status, score = _run_eval_script(checkout, run_dir, genid, round_number, task_limit, eval_kind)
            task_vector = _read_task_vector(run_dir)
            task_hash_path = run_dir / "task_set_hash"
            if round_number is None:
                evaluator = load_config(checkout / "evolve.yaml")["evaluator"]
                task_set = _effective_task_set_identity(checkout, evaluator, task_vector)
                task_set_hash = task_set.digest
            elif task_hash_path.exists():
                task_set_hash = task_hash_path.read_text().strip()
                task_set = _effective_task_set_identity(
                    checkout,
                    load_config(checkout / "evolve.yaml")["evaluator"],
                    task_vector,
                )
            else:
                raise RuntimeError("per-round evaluator did not write task_set_hash")
            evaluation_artifacts = _evaluation_artifact_reference(workspace, run_dir)
        finally:
            git(workspace, "worktree", "remove", "--force", str(checkout), check=False)

    return EvaluationResult(
        score=score,
        status=status,
        task_set_hash=task_set_hash,
        evaluator_tree=tag_evaluator_tree,
        wall_s=time.monotonic() - start,
        task_vector=task_vector,
        evaluation_artifacts=evaluation_artifacts,
        task_set_members=task_set.members,
    )


def _effective_task_set_identity(checkout: Path, evaluator: dict, _task_vector: dict | None) -> TaskSetIdentity:
    return effective_task_set_identity(checkout, evaluator)


def _read_task_vector(run_dir: Path) -> dict | None:
    path = run_dir / "task_vector.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return validate_task_vector(data)


def _evaluation_artifact_reference(workspace: Path, run_dir: Path) -> dict[str, str] | None:
    path = run_dir / "evaluation_artifacts.json"
    if not path.exists():
        return None
    return {"path": path.relative_to(workspace).as_posix(), "sha256": _sha256_file(path)}


def _run_eval_script(
    checkout: Path,
    run_dir: Path,
    genid: str,
    round_number: int | None,
    task_limit: int | None,
    eval_kind: str,
) -> tuple[str, float | None]:
    env: dict[str, str] = {**os.environ.copy(), "EVOLVE_RUN_DIR": str(run_dir), "EVOLVE_GENID": genid}
    env["EVOLVE_EVAL_KIND"] = eval_kind
    uv_cache = run_dir.parents[1] / "runtime" / "uv-cache"
    uv_cache.mkdir(parents=True, exist_ok=True)
    env["EVOLVE_UV_CACHE_DIR"] = str(uv_cache)
    if task_limit is not None:
        env["EVOLVE_TASK_LIMIT"] = str(task_limit)
    env.pop("EVOLVE_ROUND", None)
    if round_number is not None:
        env["EVOLVE_ROUND"] = str(round_number)
    result = subprocess.run(
        [str(checkout / "evaluator" / "eval.sh")],
        cwd=checkout,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    status_by_code = {0: "complete", 2: "partial", 3: "infra_failed"}
    if result.returncode not in status_by_code:
        message = result.stderr.strip() or result.stdout.strip() or "evaluator failed"
        raise RuntimeError(message)

    status = status_by_code[result.returncode]
    status_path = run_dir / "status"
    if status_path.exists():
        file_status = status_path.read_text().strip()
        if file_status and file_status != status:
            raise RuntimeError(f"evaluator status {file_status!r} conflicts with exit code {result.returncode}")

    if status == "infra_failed":
        return status, None

    score_path = run_dir / "score"
    if not score_path.exists():
        raise RuntimeError(f"evaluator did not write score for {status} result")
    return status, float(score_path.read_text().strip())


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
