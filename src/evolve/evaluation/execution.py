from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from ..config import evaluator_boolean, evaluator_sampling, experiment_id, load_config
from ..git import evaluator_tree, git, git_stdout
from ..host_runtime import clean_python_env
from ..runtime import OwnedResult, attempt_dir, next_attempt, owned_attempt_id, run_owned
from ..splits import harbor_task_pattern
from ..uv_runtime import CandidateRuntimeResult, prepare_candidate_runtime
from .evidence import trial_results, validate_task_vector
from .identity import effective_task_set_identity, evaluation_split_name
from .repair import finalize_repair, repair_task_ids
from .results import EvaluationRecord, Outcome, classify_evaluation


class EvaluationInterrupted(BaseException):
    """Carries a cancelled attempt to the driver for append-before-reraise."""


def evaluate(
    workspace: Path,
    tag: str,
    genid: str,
    *,
    purpose: str = "candidate",
    attempt: int | None = None,
    retry_of: int | None = None,
    task_limit: int | None = None,
    repair_from: EvaluationRecord | None = None,
) -> EvaluationRecord:
    evaluator_sampling(workspace)
    start = time.monotonic()
    candidate_commit = git_stdout(workspace, "rev-parse", f"{tag}^{{commit}}")
    evaluator_fingerprint = evaluator_tree(workspace, tag)
    if evaluator_fingerprint != evaluator_tree(workspace, "gen/0"):
        raise RuntimeError(f"evaluator tree for {tag} differs from gen/0")
    with tempfile.TemporaryDirectory(prefix="evolve-eval-") as tempdir:
        checkout = Path(tempdir) / "checkout"
        git(workspace, "worktree", "add", "--detach", str(checkout), candidate_commit)
        cleanup_needed = True
        try:
            evaluator = load_config(checkout / "evolve.yaml")["evaluator"]
            timeout_zero = evaluator_boolean(evaluator, "benchmark_timeout_is_zero")
            task_set = effective_task_set_identity(checkout, evaluator, purpose=purpose)
            runtime_fingerprint = hashlib.sha256((checkout / "evaluator" / "runtime.pin").read_bytes()).hexdigest()
            repair_tasks = repair_task_ids(repair_from) if repair_from is not None else ()
            if repair_from is not None and not repair_tasks:
                raise ValueError("failed-task repair requires explicit infrastructure-failed trial evidence")
            repair_selectors = _repair_task_selectors(checkout, task_set.members, purpose, repair_tasks)
            effective_limit = len(repair_tasks) if repair_tasks else task_limit
            expected = _expected_trials(
                evaluator,
                effective_limit,
                selected_tasks=len(repair_tasks) or (len(task_set.members) if task_set.members else None),
            )
            if attempt is None:
                attempt = next_attempt(
                    workspace,
                    purpose=purpose,
                    generation=genid,
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
            base: dict[str, Any] = {
                "experiment_id": experiment_id(workspace),
                "generation": genid,
                "candidate_commit": candidate_commit,
                "purpose": purpose,
                "attempt": attempt,
                "evaluator_fingerprint": evaluator_fingerprint,
                "task_set_hash": task_set.digest,
                "runtime_fingerprint": runtime_fingerprint,
                "expected_trials": expected,
                "retry_of": repair_from.attempt if repair_from is not None else retry_of,
            }
            try:
                try:
                    runtime = prepare_candidate_runtime(
                        checkout,
                        run_dir,
                        workspace / "runs" / "runtime",
                        candidate_commit,
                        evaluator,
                    )
                    base["candidate_runtime"] = _runtime_receipt_reference(workspace, runtime.receipt_path)
                    if not runtime.ready:
                        record = classify_evaluation(
                            **base,
                            trials=(),
                            setup_outcome=runtime.outcome,
                            setup_reason=runtime.reason,
                            benchmark_timeout_is_zero=timeout_zero,
                            cost_usd=0.0,
                            wall_s=time.monotonic() - start,
                            artifacts=None,
                        )
                    else:
                        result = _run_eval_script(
                            checkout,
                            run_dir,
                            genid,
                            effective_limit,
                            purpose,
                            evaluation_split_name(evaluator, purpose),
                            runtime,
                            task_names=repair_selectors,
                        )
                        setup_outcome, setup_reason = _setup_evidence(run_dir)
                        try:
                            vector = _read_task_vector(run_dir)
                            trials = trial_results(vector) if vector is not None else ()
                        except (OSError, ValueError, json.JSONDecodeError) as error:
                            trials = ()
                            setup_outcome, setup_reason = Outcome.INFRASTRUCTURE_FAILED, str(error)
                        candidate_owned = setup_outcome is Outcome.CANDIDATE_INVALID or any(
                            trial.owner == "candidate"
                            and (
                                trial.outcome is Outcome.CANDIDATE_INVALID
                                or trial.exception_type
                                or trial.exception_message
                            )
                            for trial in trials
                        )
                        complete_trial_vector = len(trials) == int(base["expected_trials"])
                        if result.returncode not in {0, 2} and not candidate_owned and not complete_trial_vector:
                            setup_outcome = Outcome.INFRASTRUCTURE_FAILED
                            setup_reason = f"evaluator exited with code {result.returncode}"
                        record = classify_evaluation(
                            **base,
                            trials=trials,
                            setup_outcome=setup_outcome,
                            setup_reason=setup_reason,
                            benchmark_timeout_is_zero=timeout_zero,
                            cost_usd=_read_cost(run_dir),
                            wall_s=time.monotonic() - start,
                            artifacts=_evaluation_artifact_reference(workspace, run_dir),
                        )
                finally:
                    cleanup_needed = False
                    git(workspace, "worktree", "remove", "--force", str(checkout), check=False)
            except Exception as error:
                return EvaluationRecord(
                    **base,
                    outcome=Outcome.INFRASTRUCTURE_FAILED,
                    reason=str(error),
                    trials=(),
                    score=None,
                    cost_usd=0.0,
                    wall_s=time.monotonic() - start,
                )
            except BaseException as error:
                record = EvaluationRecord(
                    **base,
                    outcome=Outcome.CANCELLED,
                    reason=str(error) or "evaluation cancelled",
                    trials=(),
                    score=None,
                    cost_usd=0.0,
                    wall_s=time.monotonic() - start,
                )
                raise EvaluationInterrupted(record, error) from error
            _write_attempt_summary(run_dir, record)
            return (
                finalize_repair(
                    workspace,
                    run_dir,
                    repair_from,
                    record,
                    benchmark_timeout_is_zero=timeout_zero,
                )
                if repair_from is not None
                else record
            )
        finally:
            if cleanup_needed:
                git(workspace, "worktree", "remove", "--force", str(checkout), check=False)


def _read_task_vector(run_dir: Path) -> dict | None:
    path = run_dir / "task_vector.json"
    return validate_task_vector(json.loads(path.read_text())) if path.exists() else None


def _write_attempt_summary(run_dir: Path, record: EvaluationRecord) -> None:
    (run_dir / "status").write_text(record.status + "\n")
    score_path = run_dir / "score"
    if record.score is None:
        score_path.unlink(missing_ok=True)
    else:
        score_path.write_text(f"{record.score}\n")


def _evaluation_artifact_reference(workspace: Path, run_dir: Path) -> dict[str, str] | None:
    path = run_dir / "evaluation_artifacts.json"
    return (
        {"path": path.relative_to(workspace).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if path.exists()
        else None
    )


def _runtime_receipt_reference(workspace: Path, receipt: Path | None) -> dict[str, str] | None:
    if receipt is None or not receipt.exists():
        return None
    return {
        "path": receipt.resolve().relative_to(workspace.resolve()).as_posix(),
        "sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
    }


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


def _expected_trials(evaluator: dict[str, Any], task_limit: int | None, *, selected_tasks: int | None = None) -> int:
    attempts = max(1, int(evaluator.get("k", 1)))
    tasks = selected_tasks if selected_tasks is not None else int(evaluator.get("tasks_per_round", attempts))
    if task_limit is not None:
        tasks = min(tasks, task_limit) if selected_tasks is not None else task_limit
    return max(1, tasks) * attempts


def _repair_task_selectors(
    checkout: Path,
    configured_members: tuple[str, ...],
    purpose: str,
    task_ids: tuple[str, ...],
) -> tuple[str, ...]:
    members = configured_members or _split_members(checkout, "sealed" if purpose == "anchor" else "gate")
    selectors: list[str] = []
    for task_id in task_ids:
        matches = [task_id] if task_id in members else [member for member in members if task_id.endswith(f"/{member}")]
        if len(matches) > 1:
            raise ValueError(f"ambiguous repair task selector for {task_id}: {matches}")
        selectors.append(matches[0] if matches else task_id)
    return tuple(selectors)


def _split_members(checkout: Path, split: str) -> tuple[str, ...]:
    path = checkout / "evaluator" / "splits.json"
    if not path.exists():
        return ()
    payload = json.loads(path.read_text())
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    members = tasks.get(split, []) if isinstance(tasks, dict) else []
    return tuple(str(member) for member in members) if isinstance(members, list) else ()


def _run_eval_script(
    checkout: Path,
    run_dir: Path,
    genid: str,
    task_limit: int | None,
    purpose: str,
    evaluation_split: str,
    runtime: CandidateRuntimeResult,
    *,
    task_names: tuple[str, ...] = (),
) -> OwnedResult:
    runs_dir = next(parent for parent in run_dir.parents if parent.name == "runs")
    env: dict[str, str] = {
        **clean_python_env(),
        "EVOLVE_RUN_DIR": str(run_dir),
        "EVOLVE_GENID": genid,
        "EVOLVE_EVAL_KIND": purpose,
        "EVOLVE_ATTEMPT_ID": owned_attempt_id(runs_dir.parent, run_dir),
        "EVOLVE_WORKSPACE": str(runs_dir.parent.resolve()),
    }
    env["EVOLVE_EVAL_SPLIT"] = evaluation_split
    if runtime.variant is not None:
        env["EVOLVE_CANDIDATE_RUNTIME_ENV_JSON"] = runtime.environment_json()
        env["EVOLVE_CANDIDATE_RUNTIME_MOUNTS_JSON"] = runtime.mounts_json()
    env.setdefault("EVOLVE_FRAMEWORK_PYTHON", sys.executable)
    configured_uv_cache = env.get("EVOLVE_UV_CACHE_DIR")
    uv_cache = Path(configured_uv_cache).expanduser() if configured_uv_cache else runs_dir / "runtime" / "uv-cache"
    if not uv_cache.is_absolute():
        uv_cache = runs_dir.parent / uv_cache
    uv_cache = uv_cache.resolve()
    uv_cache.mkdir(parents=True, exist_ok=True)
    env["EVOLVE_UV_CACHE_DIR"] = str(uv_cache)
    if task_limit is not None:
        env["EVOLVE_TASK_LIMIT"] = str(task_limit)
    if task_names:
        task_file = run_dir / "repair-task-names.txt"
        task_file.write_text("".join(f"{harbor_task_pattern(name)}\n" for name in task_names))
        env["EVOLVE_REPAIR_TASK_FILE"] = str(task_file)
    result = run_owned([str(checkout / "evaluator" / "eval.sh")], cwd=checkout, env=env)
    (run_dir / "stdout.log").write_text(result.stdout)
    (run_dir / "stderr.log").write_text(result.stderr)
    return result
