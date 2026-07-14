#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from harbor_artifacts import write_harbor_artifacts


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


def _write_outputs(run_dir: Path, *, status: str, metrics: dict[str, object], score: float | None = None) -> None:
    # Compatibility outputs only: the host derives its EvaluationRecord from task_vector.json.
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status").write_text(f"{status}\n")
    if score is not None:
        (run_dir / "score").write_text(f"{score}\n")
    (run_dir / "metrics.json").write_text(json.dumps({"dimensions": metrics}, indent=2, sort_keys=True) + "\n")


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        raise SystemExit("usage: parse_score.py <jobs_dir> <run_dir> <harbor_rc>")
    jobs_dir = Path(argv[1])
    run_dir = Path(argv[2])
    harbor_rc = int(argv[3])
    env_values = _load_eval_env(Path("evaluator") / "eval.env")
    expected_trials = max(
        1,
        int(
            os.environ.get(
                "EVOLVE_HARBOR_EXPECTED_TRIALS",
                env_values.get("EVOLVE_HARBOR_EXPECTED_TRIALS", env_values.get("EVOLVE_HARBOR_N", "1")),
            )
        ),
    )
    partial_floor = float(env_values.get("EVOLVE_PARTIAL_FLOOR", "0.8"))
    rewards = write_harbor_artifacts(jobs_dir, run_dir)
    completed_trials = len(rewards)
    missing_trials = max(expected_trials - completed_trials, 0)
    if harbor_rc != 0:
        _write_outputs(
            run_dir,
            status="infra_failed",
            metrics={
                "completed_trials": completed_trials,
                "expected_trials": expected_trials,
                "missing_trials": missing_trials,
                "pass_rate": 0.0,
                "harbor_rc": harbor_rc,
            },
        )
        return 3
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
