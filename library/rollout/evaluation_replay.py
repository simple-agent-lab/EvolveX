"""Replay a selected parent's certified Harbor evaluation as rollout evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from evolve.frozen import sdk
from evolve.frozen.interfaces import ArchiveView, OperatorContext, RolloutOperator, RolloutResult


def _load_collect_cases(checkout: Path) -> Callable[..., list[dict[str, Any]]]:
    path = checkout / "library" / "rollout" / "harbor.py"
    if not path.is_file():
        raise SystemExit(f"vendored Harbor rollout is missing: {path}")
    spec = importlib.util.spec_from_file_location("evolve_evaluation_replay_harbor", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load vendored Harbor rollout: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    collector = getattr(module, "collect_cases", None)
    if not callable(collector):
        raise SystemExit("vendored Harbor rollout has no collect_cases helper")
    return collector


def _certified_artifact(workspace: Path, parent: str, row: dict[str, Any]) -> Path:
    reference = row.get("artifacts")
    if not isinstance(reference, dict):
        raise SystemExit(f"selected parent {parent} has no certified evaluation artifacts")
    relative = reference.get("path")
    expected = reference.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise SystemExit(f"selected parent {parent} has malformed evaluation artifacts")
    path = (workspace / relative).resolve()
    try:
        path.relative_to(workspace.resolve())
    except ValueError as error:
        raise SystemExit("evaluation artifact path escapes workspace") from error
    if not path.is_file():
        raise SystemExit(f"evaluation artifact path is missing: {relative}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit("evaluation artifact digest mismatch")
    return path


class EvaluationReplayRollout(RolloutOperator):
    def rollout(self, checkout: Path, ctx: OperatorContext) -> RolloutResult:
        if ctx.parent is None:
            raise SystemExit("evaluation replay requires a selected parent")
        row = ArchiveView(ctx.workspace).row(ctx.parent)
        if row is None:
            raise SystemExit(f"selected parent {ctx.parent} is missing from archive")
        artifact = _certified_artifact(ctx.workspace, ctx.parent, row)
        jobs_dir = artifact.parent / "jobs"
        cases = _load_collect_cases(checkout)(
            jobs_dir,
            field_limit=int(ctx.config.get("field_limit", 2000)),
            pass_threshold=float(ctx.config.get("pass_threshold", 1.0)),
        )
        if not cases:
            raise SystemExit("evaluation replay produced no trial results")

        rollout_dir = ctx.run_dir / "rollout"
        rollout_dir.mkdir(parents=True, exist_ok=True)
        (rollout_dir / "cases.json").write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n")
        rewards = [
            float(case["reward"])
            for case in cases
            if isinstance(case.get("reward"), (int, float)) and not isinstance(case.get("reward"), bool)
        ]
        tasks = {str(case["task_name"]) for case in cases}
        counts = {
            name: sum(case.get("outcome") == name for case in cases)
            for name in ("passed", "failed", "agent_error", "infra_error", "incomplete")
        }
        return RolloutResult(
            summary={
                "variant": "evaluation_replay",
                "source_parent": ctx.parent,
                "tasks_requested": len(tasks),
                "tasks_observed": len(tasks),
                "trials_observed": len(cases),
                "passed": counts["passed"],
                "failed": counts["failed"],
                "agent_errors": counts["agent_error"],
                "infra_errors": counts["infra_error"] + counts["incomplete"],
                "mean_observed_reward": round(sum(rewards) / len(rewards), 6) if rewards else None,
                "jobs_dir": str(jobs_dir),
            },
            artifacts=[
                "rollout/cases.json",
                f"evaluation-artifacts:{artifact.relative_to(ctx.workspace)}",
            ],
        )


if __name__ == "__main__":
    sdk.main(EvaluationReplayRollout)
