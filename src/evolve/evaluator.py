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

from .git import evaluator_tree, git


@dataclass(frozen=True)
class EvaluationResult:
    score: float | None
    status: str
    task_set_hash: str
    evaluator_tree: str
    wall_s: float
    task_vector: dict | None = None  # per-task pass/fail, when the evaluator emits it


def evaluate(
    workspace: Path, tag: str, genid: str, *, round_number: int | None = None, run_name: str = "eval"
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
            status, score = _run_eval_script(checkout, run_dir, genid, round_number)
            task_hash_path = run_dir / "task_set_hash"
            if round_number is None:
                task_set_hash = _sha256_file(checkout / "evaluator" / "splits.json")
            elif task_hash_path.exists():
                task_set_hash = task_hash_path.read_text().strip()
            else:
                raise RuntimeError("per-round evaluator did not write task_set_hash")
            task_vector = _read_task_vector(run_dir)
        finally:
            git(workspace, "worktree", "remove", "--force", str(checkout), check=False)

    return EvaluationResult(
        score=score,
        status=status,
        task_set_hash=task_set_hash,
        evaluator_tree=tag_evaluator_tree,
        wall_s=time.monotonic() - start,
        task_vector=task_vector,
    )


def _read_task_vector(run_dir: Path) -> dict | None:
    path = run_dir / "task_vector.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return data if isinstance(data, dict) else None


def _run_eval_script(checkout: Path, run_dir: Path, genid: str, round_number: int | None) -> tuple[str, float | None]:
    env: dict[str, str] = {**os.environ.copy(), "EVOLVE_RUN_DIR": str(run_dir), "EVOLVE_GENID": genid}
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
