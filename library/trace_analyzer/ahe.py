"""Run official-style per-task debugger analysis for Agentic Harness Engineering."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from evolve.agent import AgentCommandError
from evolve.archive import archive_path, merged_rows
from evolve.config import operator_blocks
from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, TraceAnalyzerOperator, TraceAnalyzerResult
from library.meta_agent.runners import run_readonly_agent

Case = dict[str, Any]
ARTIFACTS = [
    "trace_analyzer/feedback.md",
    "trace_analyzer/analysis/overview.md",
    "trace_analyzer/analysis/change_evaluation.json",
    "trace_analyzer/evidence/selected.md",
    "trace_analyzer/evidence/overview.json",
    "trace_analyzer/evidence/cases.jsonl",
]
COLLECTION_LIMIT = 32
MAX_NESTING = 6
EXPANSION_FACTOR = 8
TRUNCATION_KEY = "__ahe_truncated__"
DEBUGGER_EVIDENCE_PATH = "/app/task/inputs/trace-evidence.json"
_SECRET_NAME = r"[a-z0-9_-]*(?:api[_-]?key|access[_-]?token|auth(?:orization)?|secret|password)"
_SECRET_DOUBLE_QUOTED = re.compile(rf'(?i)\b({_SECRET_NAME})\b(["\']?)(\s*[:=]\s*)"(?:\\.|[^"\\\r\n])*"')
_SECRET_SINGLE_QUOTED = re.compile(rf"(?i)\b({_SECRET_NAME})\b([\"']?)(\s*[:=]\s*)'(?:\\.|[^'\\\r\n])*'")
_BASIC_AUTHORIZATION = re.compile(rf"(?i)\b({_SECRET_NAME})\b([\"']?)(\s*[:=]\s*)(Basic)(\s+)([^\s,;}}]+)")
_SECRET_ASSIGNMENT = re.compile(
    rf"(?i)\b({_SECRET_NAME})\b([\"']?)(\s*[:=]\s*)"
    r"(?![\"'])(?!(?:Basic|Bearer)(?:\s|$))(?!\[REDACTED\])([^\s,;}]+)"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_KEY = re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|auth(?:orization)?|secret|password)")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[Case]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def _positive_int(value: object, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _nonnegative_int(value: object, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _redact(text: str) -> str:
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _SECRET_DOUBLE_QUOTED.sub(r'\1\2\3"[REDACTED]"', text)
    text = _SECRET_SINGLE_QUOTED.sub(r"\1\2\3'[REDACTED]'", text)
    text = _BASIC_AUTHORIZATION.sub(r"\1\2\3\4\5[REDACTED]", text)
    return _SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED]",
        text,
    )


def _clip(value: object, limit: int) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, sort_keys=True)
        except (TypeError, ValueError):
            text = str(value)
    text = _redact(text.strip())
    if len(text) <= limit:
        return text
    marker = "...[truncated]"
    if limit <= len(marker):
        return marker[:limit]
    return text[: limit - len(marker)] + marker


def _truncation(reason: str) -> dict[str, str]:
    return {TRUNCATION_KEY: reason}


def _bounded(
    value: object,
    limit: int,
    *,
    depth: int = 0,
    remaining: list[int] | None = None,
) -> object:
    if remaining is None:
        remaining = [COLLECTION_LIMIT * EXPANSION_FACTOR]
    if isinstance(value, str):
        return _clip(value, limit)
    if isinstance(value, list):
        if depth >= MAX_NESTING:
            return _truncation("depth")
        result = []
        reason = None
        for index, item in enumerate(value):
            if index >= COLLECTION_LIMIT:
                reason = "width"
                break
            if remaining[0] <= 0:
                reason = "expansion"
                break
            remaining[0] -= 1
            result.append(_bounded(item, limit, depth=depth + 1, remaining=remaining))
        if reason:
            result.append(_truncation(reason))
        return result
    if isinstance(value, dict):
        if depth >= MAX_NESTING:
            return _truncation("depth")
        result = {}
        reason = None
        for index, (key, item) in enumerate(value.items()):
            if index >= COLLECTION_LIMIT:
                reason = "width"
                break
            if remaining[0] <= 0:
                reason = "expansion"
                break
            remaining[0] -= 1
            clipped_key = _clip(key, limit)
            result[clipped_key] = (
                "[REDACTED]"
                if _SECRET_KEY.search(str(key))
                else _bounded(item, limit, depth=depth + 1, remaining=remaining)
            )
        if reason:
            marker = TRUNCATION_KEY
            while marker in result:
                marker += "_"
            result[marker] = reason
        return result
    return value if isinstance(value, (int, float, bool)) or value is None else _clip(value, limit)


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_cases(path: Path) -> tuple[list[Case], str | None]:
    if not path.is_file():
        return [], f"missing rollout cases: {path}"
    try:
        payload = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [], f"unreadable rollout cases: {exc}"
    if not isinstance(payload, list):
        return [], "rollout cases must be a JSON list"
    return [case for case in payload if isinstance(case, dict)], None


def _normalize(case: Case, field_limit: int) -> Case:
    all_messages = [_clip(item, field_limit) for item in _list(case.get("agent_messages")) if isinstance(item, str)]
    tool_calls = [
        {
            "name": _clip(call.get("name") or "unknown", field_limit),
            "arguments": _clip(call.get("arguments") or "", field_limit),
        }
        for call in _list(case.get("tool_calls"))
        if isinstance(call, dict)
    ]
    observations = [_clip(item, field_limit) for item in _list(case.get("observations"))]
    events = [event for event in _list(case.get("events")) if isinstance(event, dict)]
    raw_output = case.get("raw_agent_output")
    final_response = all_messages[-1] if all_messages else _clip(raw_output, field_limit) if raw_output else ""
    reward = case.get("reward")
    return {
        "trial_name": _clip(case.get("trial_name") or "", field_limit),
        "task_name": _clip(case.get("task_name") or "", field_limit),
        "outcome": _clip(case.get("outcome") or "unknown", field_limit),
        "reward": reward if isinstance(reward, (int, float)) and not isinstance(reward, bool) else None,
        "instruction": _clip(case.get("instruction") or "", field_limit),
        "agent_messages": _bounded(all_messages, field_limit),
        "tool_calls": _bounded(tool_calls, field_limit),
        "observations": _bounded(observations, field_limit),
        "events": _bounded(events, field_limit),
        "final_response": final_response,
        "verifier_output": _clip(case.get("verifier_output") or "", field_limit),
        "verifier_rewards": _bounded(_dict(case.get("verifier_rewards")), field_limit),
        "exception": _bounded(_dict(case.get("exception")), field_limit),
        "usage": _bounded(_dict(case.get("usage")), field_limit),
        "timing_s": _bounded(_dict(case.get("timing_s")), field_limit),
    }


@dataclass(frozen=True)
class TaskAnalysisJob:
    task_name: str
    cases: tuple[Case, ...]
    n_pass: int
    n_fail: int
    n_timeout: int
    mode: str


@dataclass(frozen=True)
class DebuggerResult:
    job: TaskAnalysisJob
    response: str
    usage: dict[str, Any]
    error: str | None = None


def _build_jobs(cases: list[Case], max_tasks: int) -> list[TaskAnalysisJob]:
    grouped: dict[str, list[Case]] = {}
    for case in cases:
        task_name = str(case.get("task_name") or case.get("trial_name") or "unknown")
        grouped.setdefault(task_name, []).append(case)
    jobs = []
    for task_name, task_cases in grouped.items():
        n_pass = sum(case.get("outcome") == "passed" for case in task_cases)
        n_timeout = sum(case.get("outcome") in {"timeout", "incomplete"} for case in task_cases)
        n_fail = len(task_cases) - n_pass - n_timeout
        jobs.append(
            TaskAnalysisJob(
                task_name=task_name,
                cases=tuple(task_cases),
                n_pass=n_pass,
                n_fail=n_fail,
                n_timeout=n_timeout,
                mode="debug" if n_fail or n_timeout else "summary",
            )
        )
    jobs.sort(key=lambda job: (job.mode == "summary", -(job.n_fail + job.n_timeout), job.task_name))
    return jobs[:max_tasks]


_DEBUG_K1 = """You are the AHE LLM debugger. Analyze this failed or timed-out rollout for {task_name}.
Return under 300 words using exactly these headings:
FAILURE POINT:
ROOT CAUSE:
WHAT SHOULD HAVE BEEN DONE:
GENERAL LESSON:
Ground every claim in the trace and identify a harness-level mechanism."""

_DEBUG_KN = """You are the AHE LLM debugger. Compare all {n_total} rollouts for {task_name} ({trace_labels}).
Return under 300 words using exactly these headings:
PASS vs FAIL:
FAILURE POINT:
ROOT CAUSE:
WHAT SHOULD HAVE BEEN DONE:
GENERAL LESSON:
Explain which harness behavior separates passing and failing traces."""

_SUMMARY_K1 = """You are the AHE LLM debugger. Summarize this successful rollout for {task_name}.
Return under 150 words using exactly these headings:
KEY STRATEGY:
SUCCESS FACTORS:
REUSABLE PATTERN:
FRAGILITY RISK:"""

_SUMMARY_KN = """You are the AHE LLM debugger. Compare all {n_total} successful rollouts for {task_name}.
Return under 150 words using exactly these headings:
KEY STRATEGY:
SUCCESS FACTORS:
REUSABLE PATTERN:
FRAGILITY RISK:
Identify the common harness behavior across traces."""


def _trace_labels(job: TaskAnalysisJob) -> str:
    return ", ".join(
        f"trace{index:02d}="
        + (
            "PASS"
            if case.get("outcome") == "passed"
            else "TIMEOUT"
            if case.get("outcome") in {"timeout", "incomplete"}
            else "FAIL"
        )
        for index, case in enumerate(job.cases, start=1)
    )


def _debugger_evidence(job: TaskAnalysisJob) -> str:
    return (
        json.dumps(
            {
                "task_name": job.task_name,
                "trace_labels": _trace_labels(job),
                "traces": list(job.cases),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _debugger_prompt(job: TaskAnalysisJob) -> str:
    if job.mode == "debug":
        template = _DEBUG_K1 if len(job.cases) == 1 else _DEBUG_KN
    else:
        template = _SUMMARY_K1 if len(job.cases) == 1 else _SUMMARY_KN
    return (
        template.format(
            task_name=job.task_name,
            n_total=len(job.cases),
            trace_labels=_trace_labels(job),
        )
        + "\n\n# Trace evidence\n\n"
        + f"Read the complete bounded trace evidence from `{DEBUGGER_EVIDENCE_PATH}` before writing the report."
    )


def _debugger_runner_prompt(job: TaskAnalysisJob, config: dict[str, Any]) -> str:
    prompt = _debugger_prompt(job)
    agent = str(config.get("agent") or "")
    if agent != "mini-swe-agent" and not agent.endswith(":FileTaskMiniSweAgent"):
        return prompt
    return (
        prompt + "\n\n# MiniSWE submission protocol\n\n"
        "Every response must include a Bash tool call. Use Bash to inspect the mounted evidence as needed. "
        "Write the complete requested report to `/logs/artifacts/ahe-debugger-response.md`, then finish with a "
        "standalone Bash tool call that executes `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`. Do not modify the "
        "experiment workspace."
    )


_DEBUGGER_RUNNER_KEYS = (
    "runner",
    "agent",
    "model",
    "environment",
    "image",
    "agent_kwargs",
    "agent_env",
    "agent_pythonpath",
)


def _debugger_runner_config(checkout: Path, analyzer_config: dict[str, Any]) -> dict[str, Any]:
    debugger = analyzer_config.get("debugger")
    if debugger is not None and not isinstance(debugger, dict):
        raise RuntimeError("AHE debugger configuration must be a mapping")
    source = debugger
    if source is None:
        meta = operator_blocks(checkout).get("meta_agent")
        if not isinstance(meta, dict):
            raise RuntimeError(
                "AHE debugger requires trace_analyzer.debugger configuration "
                "(or legacy operators.meta_agent configuration)"
            )
        source = meta
    config = {key: source[key] for key in _DEBUGGER_RUNNER_KEYS if key in source}
    debugger_agent_kwargs = analyzer_config.get("debugger_agent_kwargs")
    if debugger_agent_kwargs is not None:
        if not isinstance(debugger_agent_kwargs, dict):
            raise RuntimeError("AHE debugger_agent_kwargs must be a mapping")
        inherited_agent_kwargs = config.get("agent_kwargs")
        if inherited_agent_kwargs is not None and not isinstance(inherited_agent_kwargs, dict):
            raise RuntimeError("AHE debugger agent_kwargs must be a mapping")
        config["agent_kwargs"] = {
            **(inherited_agent_kwargs or {}),
            **debugger_agent_kwargs,
        }
    config["max_retries"] = 0
    if not config.get("agent") or not config.get("model"):
        raise RuntimeError("AHE debugger requires agent and model")
    return config


def _safe_task_name(task_name: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", task_name):
        return task_name
    return "task-" + hashlib.sha256(task_name.encode()).hexdigest()


def _run_debugger_job(checkout: Path, ctx: OperatorContext, job: TaskAnalysisJob) -> DebuggerResult:
    debugger = ctx.config.get("debugger")
    nested = debugger if isinstance(debugger, dict) else {}
    max_retries = _nonnegative_int(
        ctx.config.get("debugger_max_retries", nested.get("max_retries")),
        0,
    )
    attempts = max_retries + 1
    timeout_s = float(ctx.config.get("timeout_per_task") or nested.get("timeout_s") or 600)
    runner_config = _debugger_runner_config(checkout, ctx.config)
    runner_ctx = replace(ctx, config=runner_config)
    slug = _safe_task_name(job.task_name)
    last_error: AgentCommandError | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = run_readonly_agent(
                checkout,
                _debugger_runner_prompt(job, runner_config),
                runner_ctx,
                output_dir=ctx.run_dir / "trace_analyzer" / "debugger" / slug / f"attempt-{attempt}",
                job_name=f"ahe-debug-{slug}-attempt-{attempt}",
                timeout_s=timeout_s,
                input_files={"trace-evidence.json": _debugger_evidence(job)},
            )
            return DebuggerResult(job, result.output.strip(), dict(result.usage))
        except AgentCommandError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _run_debugger_job_safe(checkout: Path, ctx: OperatorContext, job: TaskAnalysisJob) -> DebuggerResult:
    try:
        return _run_debugger_job(checkout, ctx, job)
    except AgentCommandError as exc:
        error = _clip(str(exc), 500)
        response = (
            f"ANALYSIS UNAVAILABLE: The debugger failed after its configured attempts: {error}\n\n"
            f"TRACE EVIDENCE: All {len(job.cases)} bounded trace(s) remain available in the task detail and "
            "evidence files.\n\n"
            "NEXT ACTION: Do not infer a harness change from this missing analysis; inspect the preserved traces "
            "or rely on the other completed task reports."
        )
        return DebuggerResult(job, response, dict(exc.usage), error=error)


def _run_debugger_jobs(checkout: Path, ctx: OperatorContext, jobs: list[TaskAnalysisJob]) -> list[DebuggerResult]:
    if not jobs:
        raise RuntimeError("AHE debugger found no rollout tasks")
    completed = [_run_debugger_job_safe(checkout, ctx, jobs[0])]
    workers = _positive_int(ctx.config.get("max_concurrent"), 16)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run_debugger_job_safe, checkout, ctx, job) for job in jobs[1:]]
        completed.extend(future.result() for future in concurrent.futures.as_completed(futures))
    by_task = {result.job.task_name: result for result in completed}
    return [by_task[job.task_name] for job in jobs]


def _outcome_counts(cases: list[Case]) -> dict[str, int]:
    counts = Counter(str(case.get("outcome") or "unknown") for case in cases)
    items = [(name, count) for name, count in sorted(counts.items()) if name != TRUNCATION_KEY]
    if len(counts) <= COLLECTION_LIMIT and len(items) == len(counts):
        return dict(items)
    kept = dict(items[: COLLECTION_LIMIT - 1])
    kept[TRUNCATION_KEY] = len(counts) - len(kept)
    return kept


def _overview(cases: list[Case], jobs: list[TaskAnalysisJob], error: str | None) -> Case:
    rewards = [
        float(case["reward"])
        for case in cases
        if isinstance(case.get("reward"), (int, float)) and not isinstance(case.get("reward"), bool)
    ]
    return {
        "status": "error" if error else "ok",
        "error": error,
        "observed": len(cases),
        "selected": sum(len(job.cases) for job in jobs),
        "tasks": len(jobs),
        "outcomes": _outcome_counts(cases),
        "mean_reward": round(sum(rewards) / len(rewards), 6) if rewards else None,
        "cases": [
            {
                "trial_name": case.get("trial_name"),
                "task_name": case.get("task_name"),
                "outcome": case.get("outcome"),
                "reward": case.get("reward"),
            }
            for job in jobs
            for case in job.cases
        ],
    }


def _task_outcomes(cases: list[Case]) -> dict[str, str]:
    jobs = _build_jobs(cases, max(1, len(cases)))
    return {
        job.task_name: "fail" if job.n_fail or job.n_timeout else "pass" if job.n_pass else "unknown" for job in jobs
    }


def _transition(before: str | None, after: str | None) -> str:
    if before == "fail" and after == "pass":
        return "fail_to_pass"
    if before == "pass" and after == "fail":
        return "pass_to_fail"
    if before == after == "pass":
        return "unchanged_pass"
    if before == after == "fail":
        return "unchanged_fail"
    return "unknown"


def _change_verdict(predicted: list[str], fixed: list[str], realized: list[str]) -> str:
    if realized and not fixed:
        return "HARMFUL"
    if realized and fixed:
        return "MIXED"
    if predicted and len(fixed) == len(predicted):
        return "EFFECTIVE"
    if fixed:
        return "PARTIALLY_EFFECTIVE"
    return "INEFFECTIVE"


def _change_evaluation(ctx: OperatorContext, cases: list[Case], field_limit: int) -> Case:
    if ctx.parent in (None, "0"):
        return {
            "status": "baseline",
            "manifest": None,
            "transitions": {},
            "prediction_results": {},
            "risk_results": {},
            "change_evaluations": [],
            "unattributed_regressions": [],
            "summary": "baseline generation",
        }
    prior_run = ctx.workspace / "runs" / f"gen-{ctx.parent}"
    prior_raw, error = _load_cases(prior_run / "rollout" / "cases.json")
    if error:
        raise RuntimeError(error)
    manifest_path = prior_run / "meta_agent" / "change_manifest.json"
    try:
        candidate_manifest = json.loads(manifest_path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        candidate_manifest = None
    manifest = (
        candidate_manifest
        if isinstance(candidate_manifest, dict) and isinstance(candidate_manifest.get("changes"), list)
        else None
    )
    before = _task_outcomes([_normalize(case, field_limit) for case in prior_raw])
    after = _task_outcomes(cases)
    transitions = {
        task: _transition(before.get(task), after.get(task)) for task in sorted(before.keys() | after.keys())
    }
    predicted = {
        str(task)
        for change in (manifest["changes"] if manifest else [])
        if isinstance(change, dict)
        for task in change.get("predicted_fixes", [])
    }
    risks = {
        str(task)
        for change in (manifest["changes"] if manifest else [])
        if isinstance(change, dict)
        for task in change.get("risk_tasks", [])
    }
    evaluations = []
    for change in manifest["changes"] if manifest else []:
        if not isinstance(change, dict):
            continue
        change_predicted = [str(task) for task in change.get("predicted_fixes", [])]
        change_risks = [str(task) for task in change.get("risk_tasks", [])]
        fixed = [task for task in change_predicted if transitions.get(task) == "fail_to_pass"]
        still_failed = [task for task in change_predicted if task not in fixed]
        realized = [task for task in change_risks if transitions.get(task) == "pass_to_fail"]
        evaluations.append(
            {
                "change_id": str(change.get("id") or "unknown"),
                "description": str(change.get("description") or ""),
                "files": [str(path) for path in change.get("files", [])],
                "predicted_fixes": change_predicted,
                "actually_fixed": fixed,
                "still_failed": still_failed,
                "predicted_risks": change_risks,
                "risk_realized": realized,
                "verdict": _change_verdict(change_predicted, fixed, realized),
            }
        )
    unattributed = [
        task
        for task, transition in transitions.items()
        if transition == "pass_to_fail" and task not in predicted and task not in risks
    ]
    summary = ", ".join(f"{item['change_id']}: {item['verdict']}" for item in evaluations)
    return {
        "status": "evaluated",
        "manifest": str(manifest_path) if manifest else None,
        "transitions": transitions,
        "prediction_results": {
            task: "confirmed" if transitions.get(task) == "fail_to_pass" else "not_confirmed"
            for task in sorted(predicted)
        },
        "risk_results": {
            task: "realized" if transitions.get(task) == "pass_to_fail" else "not_realized" for task in sorted(risks)
        },
        "change_evaluations": evaluations,
        "unattributed_regressions": unattributed,
        "summary": summary,
    }


def _task_vector_outcome(task: Case) -> str:
    trials = _list(task.get("trials"))
    rewards = [
        float(trial["reward"])
        for trial in trials
        if isinstance(trial, dict)
        and isinstance(trial.get("reward"), (int, float))
        and not isinstance(trial.get("reward"), bool)
    ]
    if rewards and len(rewards) == len(trials) and all(reward > 0 for reward in rewards):
        return "pass"
    if rewards:
        return "fail"
    statuses = [str(trial.get("status") or "") for trial in trials if isinstance(trial, dict)]
    if statuses and all(status == "passed" for status in statuses):
        return "pass"
    if any(status in {"passed", "failed"} for status in statuses):
        return "fail"
    return "exception"


def _archive_analysis(ctx: OperatorContext) -> Case:
    rows = [
        row
        for row in merged_rows(archive_path(ctx.workspace))
        if row.get("selection_eligible") is True and isinstance(row.get("task_vector"), dict)
    ]
    scored = [
        row for row in rows if isinstance(row.get("score"), (int, float)) and not isinstance(row.get("score"), bool)
    ]
    best = max(scored, key=lambda row: float(row["score"]), default=None)
    histories: dict[str, list[str]] = {}
    for row in rows:
        tasks = _dict(_dict(row.get("task_vector")).get("tasks"))
        for task_name, task in tasks.items():
            if isinstance(task, dict):
                histories.setdefault(str(task_name), []).append(_task_vector_outcome(task))

    stability: dict[str, list[str]] = {
        "stable_pass": [],
        "stable_fail": [],
        "unstable": [],
        "possibly_unstable": [],
        "infra_only": [],
    }
    for task_name, outcomes in histories.items():
        verifier_outcomes = [outcome for outcome in outcomes if outcome in {"pass", "fail"}]
        if not verifier_outcomes:
            stability["infra_only"].append(task_name)
        elif "pass" in verifier_outcomes and "fail" in verifier_outcomes:
            key = "unstable" if len(verifier_outcomes) >= 3 else "possibly_unstable"
            stability[key].append(task_name)
        elif "pass" in verifier_outcomes:
            stability["stable_pass"].append(task_name)
        else:
            stability["stable_fail"].append(task_name)
    for tasks in stability.values():
        tasks.sort()
    return {
        "best_ever": ({"genid": str(best["genid"]), "score": float(best["score"])} if best is not None else None),
        "stability": stability,
    }


def _diagnosis_line(response: str) -> str:
    lines = [line.strip() for line in response.splitlines() if line.strip()]
    for heading in ("ROOT CAUSE:", "FAILURE POINT:"):
        for line in lines:
            if line.upper().startswith(heading) and line[len(heading) :].strip():
                return line
    return lines[0] if lines else "(empty debugger response)"


def _reports(root: Path, results: list[DebuggerResult], archive_analysis: Case) -> tuple[str, list[str]]:
    detail_dir = root / "analysis" / "detail"
    detail_dir.mkdir(parents=True, exist_ok=True)
    details: list[str] = []
    artifacts: list[str] = []
    for result in results:
        job = result.job
        labels = [
            "PASS"
            if case.get("outcome") == "passed"
            else "TIMEOUT"
            if case.get("outcome") in {"timeout", "incomplete"}
            else "FAIL"
            for case in job.cases
        ]
        failing_verifier = [
            str(case.get("verifier_output") or "") for case in job.cases if case.get("outcome") != "passed"
        ]
        detail = (
            f"# AHE Debugger Detail: {job.task_name}\n\n"
            f"- Pass: {job.n_pass}\n- Fail: {job.n_fail}\n- Timeout: {job.n_timeout}\n"
            f"- Traces: {', '.join(labels)}\n\n"
            f"## LLM debugger response\n\n{result.response}\n\n"
            f"## Failing verifier evidence\n\n{json.dumps(failing_verifier, indent=2)}\n\n"
            f"## Bounded cases\n\n```json\n{json.dumps(job.cases, indent=2, sort_keys=True)}\n```\n"
        )
        relative = f"trace_analyzer/analysis/detail/{_safe_task_name(job.task_name)}.md"
        (root.parent / relative).write_text(detail)
        workspace_relative = f"runs/{root.parent.name}/{relative}"
        details.append(
            f"# Detail: {job.task_name}\n\n"
            f"- Pass: {job.n_pass}\n- Fail: {job.n_fail}\n- Timeout: {job.n_timeout}\n"
            f"- Traces: {', '.join(labels)}\n"
            f"- Full bounded evidence: `{workspace_relative}`\n\n"
            f"## LLM debugger response\n\n{result.response}\n\n"
            f"## Failing verifier evidence\n\n{json.dumps(failing_verifier, indent=2)}\n"
        )
        artifacts.append(relative)
    lines = ["# AHE Debugger Overview", ""]
    for mode, title in (("debug", "Failures and timeouts"), ("summary", "All-pass summaries")):
        lines.extend([f"## {title}", ""])
        matches = [result for result in results if result.job.mode == mode]
        lines.extend(
            [f"- **{result.job.task_name}**: {_diagnosis_line(result.response)}" for result in matches] or ["- None"]
        )
        lines.append("")
    best = archive_analysis.get("best_ever")
    lines.extend(["## Best Ever", ""])
    if isinstance(best, dict):
        lines.append(f"- generation {best.get('genid')}: score={best.get('score')}")
    else:
        lines.append("- No eligible canonical evaluation yet")
    lines.extend(["", "## Task Stability", ""])
    stability = _dict(archive_analysis.get("stability"))
    for key, label in (
        ("stable_pass", "stable pass"),
        ("stable_fail", "stable fail"),
        ("unstable", "unstable"),
        ("possibly_unstable", "possibly unstable"),
        ("infra_only", "infrastructure only"),
    ):
        tasks = [str(task) for task in _list(stability.get(key))]
        lines.append(f"- {label} ({len(tasks)}): {', '.join(tasks) if tasks else 'None'}")
    lines.append("")
    overview = "\n".join(lines).rstrip() + "\n"
    (root / "analysis" / "overview.md").write_text(overview)
    return overview + "\n" + "\n\n".join(details), artifacts


class AheTraceAnalyzer(TraceAnalyzerOperator):
    def analyze(self, checkout: Path, ctx: OperatorContext) -> TraceAnalyzerResult:
        raw_cases, error = _load_cases(ctx.run_dir / "rollout" / "cases.json")
        if error:
            raise RuntimeError(error)
        field_limit = _positive_int(ctx.config.get("field_limit"), 2000)
        cases = [_normalize(case, field_limit) for case in raw_cases]
        jobs = _build_jobs(cases, _positive_int(ctx.config.get("max_tasks"), 90))
        results = _run_debugger_jobs(checkout, ctx, jobs)
        overview = _overview(cases, jobs, None)
        root = ctx.run_dir / "trace_analyzer"
        evidence = root / "evidence"
        root.mkdir(parents=True, exist_ok=True)
        evidence.mkdir(parents=True, exist_ok=True)
        rendered, detail_artifacts = _reports(root, results, _archive_analysis(ctx))
        (root / "feedback.md").write_text(rendered)
        (evidence / "selected.md").write_text(rendered)
        _write_json(evidence / "overview.json", overview)
        selected = [case for job in jobs for case in job.cases]
        _write_jsonl(evidence / "cases.jsonl", selected)
        change_evaluation = _change_evaluation(ctx, cases, field_limit)
        _write_json(root / "analysis" / "change_evaluation.json", change_evaluation)
        summary = {key: value for key, value in overview.items() if key != "cases"}
        summary["debugger_usd"] = round(sum(float(result.usage.get("usd") or 0) for result in results), 6)
        summary["debugger_errors"] = sum(result.error is not None for result in results)
        return TraceAnalyzerResult(summary=summary, artifacts=[*ARTIFACTS, *detail_artifacts])


if __name__ == "__main__":
    sdk.main(AheTraceAnalyzer)
