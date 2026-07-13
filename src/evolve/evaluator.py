from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .config import evaluator_boolean, experiment_id, load_config
from .evaluation import EvaluationRecord, Outcome, classify_evaluation
from .git import evaluator_tree, git, git_stdout
from .runtime import attempt_dir, next_attempt
from .task_sets import TaskSetIdentity, effective_task_set_identity
from .task_vectors import trial_results, validate_task_vector


def evaluate(
    workspace: Path,
    tag: str,
    genid: str,
    *,
    purpose: str = "candidate",
    attempt: int | None = None,
    retry_of: int | None = None,
    round_number: int | None = None,
    task_limit: int | None = None,
) -> EvaluationRecord:
    start = time.monotonic()
    candidate_commit = git_stdout(workspace, "rev-parse", f"{tag}^{{commit}}")
    evaluator_fingerprint = evaluator_tree(workspace, tag)
    if evaluator_fingerprint != evaluator_tree(workspace, "gen/0"):
        raise RuntimeError(f"evaluator tree for {tag} differs from gen/0")
    if attempt is None:
        attempt = next_attempt(
            workspace, purpose=purpose, generation=genid,
            candidate_commit=candidate_commit,
        )
    run_dir = attempt_dir(
        workspace,
        purpose=purpose,
        generation=genid,
        candidate_commit=candidate_commit,
        attempt=attempt,
    )
    run_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="evolve-eval-") as tempdir:
        checkout = Path(tempdir) / "checkout"
        git(workspace, "worktree", "add", "--detach", str(checkout), candidate_commit)
        try:
            evaluator = load_config(checkout / "evolve.yaml")["evaluator"]
            timeout_zero = evaluator_boolean(evaluator, "benchmark_timeout_is_zero")
            result = _run_eval_script(checkout, run_dir, genid, round_number, task_limit, purpose)
            task_set = _effective_task_set_identity(checkout, evaluator, None)
            task_hash = run_dir / "task_set_hash"
            if round_number is not None and task_hash.exists():
                task_set = TaskSetIdentity(task_hash.read_text().strip(), task_set.members)
            setup_outcome, setup_reason = _setup_evidence(run_dir)
            try:
                vector = _read_task_vector(run_dir)
                trials = trial_results(vector) if vector is not None else ()
            except (OSError, ValueError, json.JSONDecodeError) as error:
                trials = ()
                setup_outcome, setup_reason = Outcome.INFRASTRUCTURE_FAILED, str(error)
            candidate_owned = setup_outcome is Outcome.CANDIDATE_INVALID or any(
                trial.owner == "candidate"
                and (trial.outcome is Outcome.CANDIDATE_INVALID or trial.exception_type or trial.exception_message)
                for trial in trials
            )
            if result.returncode not in {0, 2} and not candidate_owned:
                setup_outcome = Outcome.INFRASTRUCTURE_FAILED
                setup_reason = f"evaluator exited with code {result.returncode}"
            cost_usd = _read_cost(run_dir)
            runtime_fingerprint = _sha256_file(checkout / "evaluator" / "runtime.pin")
            artifacts = _evaluation_artifact_reference(workspace, run_dir)
            expected = _expected_trials(evaluator, task_limit)
            return classify_evaluation(
                experiment_id=experiment_id(workspace), generation=genid,
                candidate_commit=candidate_commit, purpose=purpose, attempt=attempt,
                evaluator_fingerprint=evaluator_fingerprint, task_set_hash=task_set.digest,
                runtime_fingerprint=runtime_fingerprint, expected_trials=expected,
                trials=trials, setup_outcome=setup_outcome, setup_reason=setup_reason,
                benchmark_timeout_is_zero=timeout_zero,
                cost_usd=cost_usd, wall_s=time.monotonic() - start,
                retry_of=retry_of, artifacts=artifacts,
            )
        finally:
            git(workspace, "worktree", "remove", "--force", str(checkout), check=False)


def _effective_task_set_identity(checkout: Path, evaluator: dict, _vector: dict | None) -> TaskSetIdentity:
    return effective_task_set_identity(checkout, evaluator)


def _read_task_vector(run_dir: Path) -> dict | None:
    path = run_dir / "task_vector.json"
    return validate_task_vector(json.loads(path.read_text())) if path.exists() else None


def _evaluation_artifact_reference(workspace: Path, run_dir: Path) -> dict[str, str] | None:
    path = run_dir / "evaluation_artifacts.json"
    return {"path": path.relative_to(workspace).as_posix(), "sha256": _sha256_file(path)} if path.exists() else None


def _setup_evidence(run_dir: Path) -> tuple[Outcome | None, str | None]:
    path = run_dir / "setup_outcome"
    if not path.exists():
        return None, None
    outcome = Outcome(path.read_text().strip())
    reason = run_dir / "setup_reason"
    return outcome, reason.read_text().strip() if reason.exists() else f"evaluator reported {outcome.value}"


def _read_cost(run_dir: Path) -> float:
    path = run_dir / "cost.json"
    if not path.exists():
        return 0.0
    value = json.loads(path.read_text()).get("usd")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("evaluator cost.json must contain numeric usd")
    return float(value)


def _expected_trials(evaluator: dict[str, Any], task_limit: int | None) -> int:
    attempts = max(1, int(evaluator.get("k", 1)))
    tasks = task_limit if task_limit is not None else int(evaluator.get("tasks_per_round", attempts))
    return max(1, tasks) * attempts


def _run_eval_script(
    checkout: Path, run_dir: Path, genid: str, round_number: int | None,
    task_limit: int | None, purpose: str,
) -> subprocess.CompletedProcess[str]:
    env: dict[str, str] = {**os.environ, "EVOLVE_RUN_DIR": str(run_dir), "EVOLVE_GENID": genid,
                           "EVOLVE_EVAL_KIND": purpose}
    runs_dir = next(parent for parent in run_dir.parents if parent.name == "runs")
    uv_cache = runs_dir / "runtime" / "uv-cache"
    uv_cache.mkdir(parents=True, exist_ok=True)
    env["EVOLVE_UV_CACHE_DIR"] = str(uv_cache)
    if task_limit is not None:
        env["EVOLVE_TASK_LIMIT"] = str(task_limit)
    env.pop("EVOLVE_ROUND", None)
    if round_number is not None:
        env["EVOLVE_ROUND"] = str(round_number)
    result = subprocess.run([str(checkout / "evaluator" / "eval.sh")], cwd=checkout,
                            env=env, text=True, capture_output=True, check=False)
    (run_dir / "stdout.log").write_text(result.stdout)
    (run_dir / "stderr.log").write_text(result.stderr)
    return result


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
