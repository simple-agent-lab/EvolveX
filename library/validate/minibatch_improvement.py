"""Validate a GEPA proposal on the exact Harbor minibatch used by its parent."""

# ruff: noqa: E402

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, ValidateOperator, ValidateResult
from library.gepa_support import read_json
from library.rollout.harbor import HarborRollout


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _cases(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def _task_scores(cases: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for case in cases:
        task_name = str(case.get("task_name") or "")
        if not task_name:
            continue
        reward = case.get("reward")
        grouped[task_name].append(
            float(reward) if isinstance(reward, (int, float)) and not isinstance(reward, bool) else 0.0
        )
    return {task_name: sum(values) / len(values) for task_name, values in grouped.items()}


def _infra_cases(cases: list[dict[str, Any]]) -> list[str]:
    return [
        str(case.get("task_name") or case.get("trial_name") or "unknown")
        for case in cases
        if case.get("outcome") in {"infra_error", "incomplete"}
    ]


class MinibatchImprovementValidate(ValidateOperator):
    def validate(self, checkout: Path, ctx: OperatorContext) -> ValidateResult:
        parent_path = ctx.run_dir / "rollout" / "cases.json"
        parent_cases = _cases(parent_path)
        if not parent_cases:
            raise SystemExit(f"GEPA validation requires parent Harbor cases: {parent_path}")
        parent_infra = _infra_cases(parent_cases)
        parent_scores = _task_scores(parent_cases)
        if not parent_scores:
            raise SystemExit("GEPA parent minibatch contains no named tasks")

        child_run_dir = ctx.run_dir / "validate" / "child-eval"
        child_config = {
            key: value for key, value in ctx.config.items() if key not in {"variant", "timeout_s", "criterion"}
        }
        child_config.update(
            {
                "split": "train",
                "task_names": list(parent_scores),
                "budget_tasks": len(parent_scores),
            }
        )
        child_ctx = OperatorContext(
            workspace=ctx.workspace,
            checkout=checkout,
            run_dir=child_run_dir,
            genid=f"{ctx.genid}-gepa-child",
            parent=ctx.parent,
            round=ctx.round,
            fan_out=ctx.fan_out,
            config=child_config,
            rng=ctx.rng,
        )
        rollout_result = HarborRollout().rollout(checkout, child_ctx)
        _write_json(child_run_dir / "rollout" / "summary.json", rollout_result.summary)
        _write_json(child_run_dir / "rollout" / "artifacts.json", rollout_result.artifacts)
        child_cases_path = child_run_dir / "rollout" / "cases.json"
        child_cases = _cases(child_cases_path)
        child_infra = _infra_cases(child_cases)
        child_scores = _task_scores(child_cases)
        if set(child_scores) != set(parent_scores):
            missing = sorted(set(parent_scores) - set(child_scores))
            extra = sorted(set(child_scores) - set(parent_scores))
            raise SystemExit(f"GEPA child minibatch mismatch; missing={missing}, extra={extra}")

        parent_total = sum(parent_scores.values())
        child_total = sum(child_scores.values())
        criterion = str(ctx.config.get("criterion") or "strict")
        if criterion == "strict":
            accept = child_total > parent_total
        elif criterion == "non_decreasing":
            accept = child_total >= parent_total
        else:
            raise ValueError("criterion must be 'strict' or 'non_decreasing'")
        comparison = {
            "criterion": criterion,
            "task_names": list(parent_scores),
            "parent_scores": parent_scores,
            "child_scores": child_scores,
            "parent_total": parent_total,
            "child_total": child_total,
            "delta": child_total - parent_total,
            "accepted": accept,
            "parent_infra_cases": parent_infra,
            "child_infra_cases": child_infra,
        }
        root = ctx.run_dir / "validate"
        _write_json(root / "comparison.json", comparison)
        _write_json(root / "parent-cases.json", parent_cases)
        _write_json(root / "child-cases.json", child_cases)
        reason = (
            f"GEPA minibatch improved by {child_total - parent_total:.6g}"
            if accept
            else f"GEPA minibatch did not improve: delta {child_total - parent_total:.6g}"
        )
        return ValidateResult(
            accept=accept,
            reason=reason,
            artifacts=[
                "validate/comparison.json",
                "validate/parent-cases.json",
                "validate/child-cases.json",
                "validate/child-eval/rollout/summary.json",
                "validate/child-eval/rollout/cases.json",
                "validate/child-eval/rollout/harbor.log",
            ],
        )


if __name__ == "__main__":
    sdk.main(MinibatchImprovementValidate)
