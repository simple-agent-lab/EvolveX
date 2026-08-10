"""Validate a GEPA proposal on the exact Harbor minibatch used by its parent."""

# ruff: noqa: E402

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, ValidateOperator, ValidateResult
from library._shared.config import (
    config_object,
    mapping,
    nonnegative_int,
    positive_float,
    positive_int,
    reject_unknown,
    string,
)
from library._shared.gepa import read_json
from library._shared.harbor import HarborRollout

_CONFIG_KEYS = {
    "criterion",
    "n_concurrent",
    "agent_setup_timeout_multiplier",
    "agent_timeout_multiplier",
    "verifier_timeout_multiplier",
    "max_retries",
    "environment",
    "environment_kwargs",
}


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, _CONFIG_KEYS)
    criterion = string(config, "criterion", "strict")
    if criterion not in {"strict", "non_decreasing"}:
        raise ValueError("criterion must be 'strict' or 'non_decreasing'")
    normalized: dict[str, object] = {"criterion": criterion}
    if "max_retries" in config:
        normalized["max_retries"] = nonnegative_int(config, "max_retries", 0)
    if "n_concurrent" in config:
        normalized["n_concurrent"] = positive_int(config, "n_concurrent", 1)
    for key in ("agent_setup_timeout_multiplier", "agent_timeout_multiplier", "verifier_timeout_multiplier"):
        if key in config:
            normalized[key] = positive_float(config, key, 1.0)
    if "environment" in config:
        normalized["environment"] = string(config, "environment", "")
    if "environment_kwargs" in config:
        normalized["environment_kwargs"] = mapping(config, "environment_kwargs", {})
    return normalized


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _cases(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    return (
        [{str(key): value for key, value in row.items()} for row in payload if isinstance(row, dict)]
        if isinstance(payload, list)
        else []
    )


def _task_scores(cases: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for case in cases:
        task_name = str(case.get("task_name") or "")
        if not task_name or case.get("outcome") in {"infra_error", "incomplete"}:
            continue
        reward = case.get("reward")
        if not isinstance(reward, (int, float)) or isinstance(reward, bool) or not math.isfinite(float(reward)):
            continue
        grouped[task_name].append(float(reward))
    return {task_name: sum(values) / len(values) for task_name, values in grouped.items()}


def _task_names(cases: list[dict[str, Any]]) -> list[str]:
    return list(
        dict.fromkeys(
            str(case.get("task_name"))
            for case in cases
            if isinstance(case.get("task_name"), str) and case.get("task_name")
        )
    )


def _unscorable_cases(cases: list[dict[str, Any]]) -> list[str]:
    unscorable = []
    for case in cases:
        reward = case.get("reward")
        if case.get("outcome") in {"infra_error", "incomplete"} or (
            not isinstance(reward, (int, float)) or isinstance(reward, bool) or not math.isfinite(float(reward))
        ):
            unscorable.append(str(case.get("task_name") or case.get("trial_name") or "unknown"))
    return unscorable


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
        parent_task_names = _task_names(parent_cases)
        if not parent_task_names:
            raise SystemExit("GEPA parent minibatch contains no named tasks")
        parent_infra = _infra_cases(parent_cases)
        parent_unscorable = _unscorable_cases(parent_cases)
        parent_scores = _task_scores(parent_cases)

        child_run_dir = ctx.run_dir / "validate" / "child-eval"
        child_config = {
            key: value for key, value in ctx.config.items() if key not in {"variant", "timeout_s", "criterion"}
        }
        child_config.update(
            {
                "split": "train",
                "task_names": parent_task_names,
                "budget_tasks": len(parent_task_names),
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
            timeout_s=ctx.timeout_s,
        )
        rollout_result = HarborRollout().rollout(checkout, child_ctx)
        _write_json(child_run_dir / "rollout" / "summary.json", rollout_result.summary)
        _write_json(child_run_dir / "rollout" / "artifacts.json", rollout_result.artifacts)
        child_cases_path = child_run_dir / "rollout" / "cases.json"
        child_cases = _cases(child_cases_path)
        child_infra = _infra_cases(child_cases)
        child_unscorable = _unscorable_cases(child_cases)
        child_scores = _task_scores(child_cases)
        child_task_names = _task_names(child_cases)
        if set(child_task_names) != set(parent_task_names):
            missing = sorted(set(parent_task_names) - set(child_task_names))
            extra = sorted(set(child_task_names) - set(parent_task_names))
            raise SystemExit(f"GEPA child minibatch mismatch; missing={missing}, extra={extra}")

        parent_total = sum(parent_scores.values())
        child_total = sum(child_scores.values())
        criterion = str(ctx.config.get("criterion") or "strict")
        if criterion == "strict":
            score_accept = child_total > parent_total
        elif criterion == "non_decreasing":
            score_accept = child_total >= parent_total
        else:
            raise ValueError("criterion must be 'strict' or 'non_decreasing'")
        comparison_complete = not parent_unscorable and not child_unscorable
        accept = comparison_complete and score_accept
        comparison = {
            "criterion": criterion,
            "task_names": parent_task_names,
            "parent_scores": parent_scores,
            "child_scores": child_scores,
            "parent_total": parent_total,
            "child_total": child_total,
            "delta": child_total - parent_total,
            "accepted": accept,
            "comparison_complete": comparison_complete,
            "parent_infra_cases": parent_infra,
            "child_infra_cases": child_infra,
            "parent_unscorable_cases": parent_unscorable,
            "child_unscorable_cases": child_unscorable,
        }
        root = ctx.run_dir / "validate"
        _write_json(root / "comparison.json", comparison)
        _write_json(root / "parent-cases.json", parent_cases)
        _write_json(root / "child-cases.json", child_cases)
        if not comparison_complete:
            reason = "GEPA minibatch comparison is incomplete due to infrastructure or missing reward results"
        elif accept:
            reason = f"GEPA minibatch improved by {child_total - parent_total:.6g}"
        else:
            reason = f"GEPA minibatch did not improve: delta {child_total - parent_total:.6g}"
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
    sdk.main(MinibatchImprovementValidate, validate_config=validate_config)
