"""Run the official-style behavior-only trajectory judge for A-Evolve."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from evolve.agent import AgentCommandError
from evolve.config import operator_blocks
from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, TraceAnalyzerOperator, TraceAnalyzerResult
from evolve.trace_analysis import (
    _load_cases,
    _positive_int,
    _trajectory_only_cases,
    trajectory_signal_records,
    write_evidence_bundle,
)
from library.meta_agent.runners import run_readonly_agent

Case = dict[str, Any]

JUDGE_SYSTEM_PROMPT = """You are evaluating whether an AI agent successfully completed a command-line task.
You can ONLY see the agent's actions (commands run and their outputs). You do NOT have access to actual test
results. Based on the trajectory, estimate whether the task was completed successfully."""

JUDGE_USER_TEMPLATE = """Task: {task_id}

Agent trajectory:
{trajectory}

Evaluate the agent from this behavior alone:
1. Score from 0 to 10 (0 complete failure, 5 partial progress, 10 likely fully solved).
2. Category (for example build, debug, data-science, security, scientific, system-admin, software-engineering).
3. One-sentence outcome.
4. A concrete failure reason when score is below 7.

Return only this JSON object:
{{"score": N, "category": "...", "outcome": "...", "failure_reason": "..."}}"""

_RUNNER_KEYS = (
    "agent",
    "model",
    "environment",
    "image",
    "agent_kwargs",
    "agent_env",
    "agent_pythonpath",
)


def _runner_config(checkout: Path) -> dict[str, Any]:
    meta = operator_blocks(checkout).get("meta_agent")
    if not isinstance(meta, dict):
        raise RuntimeError("trajectory_only judge requires operators.meta_agent configuration")
    config = {key: meta[key] for key in _RUNNER_KEYS if key in meta}
    config["max_retries"] = 0
    if not config.get("agent") or not config.get("model"):
        raise RuntimeError("trajectory_only judge requires meta-agent agent and model")
    return config


def _safe_slug(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", value):
        return value
    return "task-" + hashlib.sha256(value.encode()).hexdigest()


def _runner_prompt(record: Case, config: dict[str, Any]) -> str:
    prompt = (
        JUDGE_SYSTEM_PROMPT
        + "\n\n"
        + JUDGE_USER_TEMPLATE.format(
            task_id=record.get("task_id") or "unknown",
            trajectory=record.get("compressed_trajectory") or "",
        )
    )
    agent = str(config.get("agent") or "")
    if agent != "mini-swe-agent" and not agent.endswith(":FileTaskMiniSweAgent"):
        return prompt
    return (
        prompt + "\n\nUse Bash only to write the JSON object to "
        "`/logs/artifacts/ahe-debugger-response.md`, then run "
        "`echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`. Do not inspect or modify the experiment workspace."
    )


def _json_object(text: str) -> Case:
    stripped = text.strip()
    if "```" in stripped:
        blocks = stripped.split("```")
        candidates = [block.removeprefix("json").strip() for block in blocks[1::2]]
    else:
        candidates = [stripped]
    candidates.extend(re.findall(r"\{(?:[^{}]|\"(?:\\.|[^\"\\])*\")*\}", stripped, flags=re.DOTALL))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        score = payload.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            continue
        return {
            "score": max(0, min(10, score)),
            "category": str(payload.get("category") or "unknown"),
            "outcome": str(payload.get("outcome") or ""),
            "failure_reason": str(payload.get("failure_reason") or ""),
        }
    raise ValueError("judge response did not contain the required JSON object")


def _judge_one(
    checkout: Path,
    ctx: OperatorContext,
    config: dict[str, Any],
    record: Case,
    index: int,
) -> Case:
    attempts = _positive_int(ctx.config.get("judge_retry_attempts"), 3)
    timeout_s = float(ctx.config.get("judge_timeout_s") or 600)
    runner_ctx = replace(ctx, config=config)
    slug = _safe_slug(str(record.get("task_id") or f"task-{index}"))
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            result = run_readonly_agent(
                checkout,
                _runner_prompt(record, config),
                runner_ctx,
                output_dir=ctx.run_dir / "trace_analyzer" / "judge" / f"{index:04d}-{slug}" / f"attempt-{attempt}",
                job_name=f"trajectory-judge-{index:04d}-{slug}-attempt-{attempt}",
                timeout_s=timeout_s,
            )
            return _json_object(result.output)
        except (AgentCommandError, OSError, RuntimeError, ValueError) as exc:
            last_error = str(exc)
    return {
        "score": -1,
        "category": "unknown",
        "outcome": f"judge error: {last_error[:200]}",
        "failure_reason": "",
    }


def _judge_records(checkout: Path, ctx: OperatorContext, records: list[Case]) -> list[Case]:
    if not records:
        return []
    config = _runner_config(checkout)
    workers = _positive_int(ctx.config.get("judge_max_concurrent"), 4)
    verdicts: list[Case | None] = [None] * len(records)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_judge_one, checkout, ctx, config, record, index): index for index, record in enumerate(records)
        }
        for future in concurrent.futures.as_completed(futures):
            verdicts[futures[future]] = future.result()
    return [verdict or {"score": -1} for verdict in verdicts]


class TrajectoryOnly(TraceAnalyzerOperator):
    def analyze(self, checkout: Path, ctx: OperatorContext) -> TraceAnalyzerResult:
        cases_path = ctx.run_dir / "rollout" / "cases.json"
        current = _load_cases(cases_path)
        cases = _trajectory_only_cases(ctx, current)
        records = trajectory_signal_records(cases)
        verdicts = _judge_records(checkout, ctx, records)
        max_chars = _positive_int(ctx.config.get("max_chars"), 30_000)
        feedback, artifacts = write_evidence_bundle(
            ctx.run_dir,
            cases,
            variant="trajectory_only",
            max_chars=max_chars,
            judge_verdicts=verdicts,
        )
        (ctx.run_dir / "trace_analyzer" / "feedback.md").write_text(feedback)
        return TraceAnalyzerResult(
            summary={
                "variant": "trajectory_only",
                "cases": len(records),
                "judge_verdicts": sum(1 for verdict in verdicts if verdict.get("score", -1) >= 0),
                "source": str(cases_path),
            },
            artifacts=["trace_analyzer/feedback.md", *artifacts],
        )


if __name__ == "__main__":
    sdk.main(TrajectoryOnly)
