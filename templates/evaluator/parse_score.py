#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_eval_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")
    return values


def _reward_from_trial(trial_dir: Path) -> float | None:
    result_path = trial_dir / "result.json"
    if result_path.exists():
        try:
            payload = json.loads(result_path.read_text())
        except json.JSONDecodeError:
            payload = {}
        rewards = (payload.get("verifier_result") or {}).get("rewards", {})
        reward = rewards.get("reward")
        if isinstance(reward, (int, float)):
            return float(reward)
    reward_path = trial_dir / "verifier" / "reward.txt"
    if reward_path.exists():
        try:
            return float(reward_path.read_text().strip())
        except ValueError:
            return None
    return None


def _write_outputs(run_dir: Path, *, status: str, metrics: dict[str, object], score: float | None = None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status").write_text(f"{status}\n")
    if score is not None:
        (run_dir / "score").write_text(f"{score}\n")
    (run_dir / "metrics.json").write_text(json.dumps({"dimensions": metrics}, indent=2, sort_keys=True) + "\n")


def _expected_trials(run_dir: Path, env_values: dict[str, str]) -> int:
    selection = run_dir / "task-split.json"
    if selection.exists():
        payload = json.loads(selection.read_text())
        tasks = payload.get("tasks") if isinstance(payload, dict) else None
        if isinstance(tasks, list):
            return max(1, len(tasks) * int(env_values.get("EVOLVE_HARBOR_K", "1")))
    return max(1, int(env_values.get("EVOLVE_HARBOR_EXPECTED_TRIALS", env_values.get("EVOLVE_HARBOR_N", "1"))))


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        raise SystemExit("usage: parse_score.py <jobs_dir> <run_dir>")
    jobs_dir = Path(argv[1])
    run_dir = Path(argv[2])
    env_values = _load_eval_env(Path("evaluator") / "eval.env")
    expected_trials = _expected_trials(run_dir, env_values)
    partial_floor = float(env_values.get("EVOLVE_PARTIAL_FLOOR", "0.8"))
    rewards = []
    pending = list(sorted(jobs_dir.iterdir())) if jobs_dir.exists() else []
    for child in pending:
        if not child.is_dir():
            continue
        reward = _reward_from_trial(child)
        if reward is not None:
            rewards.append(reward)
            continue
        pending.extend(sorted(grandchild for grandchild in child.iterdir() if grandchild.is_dir()))
    completed_trials = len(rewards)
    missing_trials = max(expected_trials - completed_trials, 0)
    if completed_trials == 0:
        _write_outputs(
            run_dir,
            status="infra_failed",
            metrics={
                "completed_trials": 0,
                "expected_trials": expected_trials,
                "missing_trials": expected_trials,
                "pass_rate": 0.0,
            },
        )
        return 3

    score = sum(rewards) / completed_trials
    metrics = {
        "completed_trials": completed_trials,
        "expected_trials": expected_trials,
        "missing_trials": missing_trials,
        "pass_rate": score,
    }
    completion_ratio = completed_trials / expected_trials
    if completed_trials < expected_trials:
        status = "partial" if completion_ratio >= partial_floor else "infra_failed"
        _write_outputs(run_dir, status=status, metrics=metrics, score=score if status == "partial" else None)
        return 2 if status == "partial" else 3

    _write_outputs(run_dir, status="complete", metrics=metrics, score=score)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
