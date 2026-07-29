"""Shared deterministic trace analysis used by workspace analyzer variants."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from evolve.frozen.interfaces import OperatorContext, TraceAnalyzerOperator, TraceAnalyzerResult

Case = dict[str, Any]

VARIANTS = (
    "failure_patterns",
    "failed_traces",
    "trace_browser",
    "trajectory_only",
    "execution_records",
    "utility_metrics",
)


def normalize_variant(value: object) -> str:
    variant = str(value or "failure_patterns").strip().lower().replace("-", "_")
    if variant not in VARIANTS:
        supported = ", ".join(VARIANTS)
        raise ValueError(f"unknown trace analyzer variant {variant!r}; choose one of: {supported}")
    return variant


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[Case]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def _clip(text: object, limit: int = 1200) -> str:
    value = str(text or "").strip()
    return value if len(value) <= limit else value[:limit] + f"\n...[truncated {len(value) - limit} chars]..."


def _tool_sequence(case: Case) -> list[str]:
    return [str(call.get("name") or "unknown") for call in case.get("tool_calls") or [] if isinstance(call, dict)]


def _failure_cause(case: Case) -> str:
    outcome = str(case.get("outcome") or "unknown")
    exception = case.get("exception") or {}
    exception_type = str(exception.get("type") or "")
    evidence = "\n".join(
        [
            exception_type,
            str(exception.get("message") or ""),
            str(case.get("verifier_output") or ""),
        ]
    ).lower()
    categories = (
        ("timeout", r"time(?:d)?\s*out|timeout"),
        ("missing_artifact", r"missing|required (?:file|artifact)|not found|no such file"),
        ("format_or_parse", r"invalid (?:json|format)|parse|schema|malformed"),
        ("test_or_assertion", r"assert|test[s]? failed|failure|expected.+(?:got|actual)"),
        ("dependency_or_environment", r"module not found|no module named|dependency|docker|network|download"),
        ("permission", r"permission denied|not permitted|unauthorized"),
    )
    for name, pattern in categories:
        if re.search(pattern, evidence):
            return name
    if exception_type:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", exception_type).lower()
    return "verifier_rejection" if outcome == "failed" else outcome


def _trace_mechanism(case: Case, cause: str) -> tuple[str, str, list[str]]:
    calls = case.get("tool_calls") or []
    observations = "\n".join(str(item) for item in case.get("observations") or [])
    normalized_calls = [
        (str(call.get("name") or "unknown"), str(call.get("arguments") or ""))
        for call in calls
        if isinstance(call, dict)
    ]
    repeats = [item for item, count in Counter(normalized_calls).items() if count > 1]
    symptoms: list[str] = []
    if repeats:
        symptoms.append("repeated identical tool action: %s" % ", ".join(name for name, _ in repeats[:3]))
    if re.search(r"\b(error|failed|exception|traceback|not found)\b", observations, re.I):
        symptoms.append("tool observations contain an error")
    if cause == "missing_artifact":
        mechanism = "artifact_management"
        causal = "agent_behavior_likely_causal"
    elif cause == "timeout" and (repeats or len(calls) >= 8):
        mechanism = "unproductive_tool_loop"
        causal = "agent_behavior_likely_causal"
    elif repeats:
        mechanism = "repeated_action_without_adaptation"
        causal = "agent_behavior_contributing"
    elif re.search(r"\b(error|failed|exception|traceback)\b", observations, re.I):
        mechanism = "tool_error_recovery"
        causal = "agent_behavior_contributing"
    elif case.get("outcome") in {"infra_error", "incomplete"}:
        mechanism = "runtime_or_harness_boundary"
        causal = "causality_unresolved"
    elif not calls:
        mechanism = "insufficient_environment_interaction"
        causal = "agent_behavior_likely_causal"
    elif case.get("outcome") == "agent_error":
        mechanism = "agent_runtime_failure"
        causal = "agent_behavior_or_runtime"
    else:
        mechanism = "task_strategy_or_verification"
        causal = "causality_unresolved"
    if not symptoms:
        symptoms.append("verifier rejected the final environment state")
    return mechanism, causal, symptoms


def failure_records(cases: list[Case]) -> list[Case]:
    records: list[Case] = []
    for case in cases:
        if case.get("outcome") == "passed":
            continue
        cause = _failure_cause(case)
        mechanism, causal_status, symptoms = _trace_mechanism(case, cause)
        records.append(
            {
                "trial_name": case.get("trial_name"),
                "task_name": case.get("task_name"),
                "reward": case.get("reward"),
                "terminal_cause": cause,
                "causal_status": causal_status,
                "agent_mechanism": mechanism,
                "shared_trace_symptoms": symptoms,
                "instruction": case.get("instruction"),
                "agent_messages": case.get("agent_messages"),
                "tool_calls": case.get("tool_calls"),
                "observations": case.get("observations"),
                "verifier_evidence": case.get("verifier_output"),
                "exception": case.get("exception"),
            }
        )
    return records


def cluster_failure_patterns(records: list[Case]) -> list[Case]:
    clusters: dict[tuple[str, str, str], list[Case]] = defaultdict(list)
    for record in records:
        signature = (
            str(record["terminal_cause"]),
            str(record["causal_status"]),
            str(record["agent_mechanism"]),
        )
        clusters[signature].append(record)
    patterns: list[Case] = []
    for index, (signature, members) in enumerate(
        sorted(clusters.items(), key=lambda item: (-len(item[1]), item[0])), start=1
    ):
        representative = members[:3]
        patterns.append(
            {
                "id": f"failure-pattern-{index}",
                "signature": {
                    "terminal_cause": signature[0],
                    "causal_status": signature[1],
                    "agent_mechanism": signature[2],
                },
                "support": len(members),
                "actionable": signature[1] != "not_attributed_to_agent",
                "task_names": [member.get("task_name") for member in members],
                "shared_trace_symptoms": sorted(
                    {symptom for member in members for symptom in member.get("shared_trace_symptoms") or []}
                ),
                "representatives": [
                    {
                        "task_name": member.get("task_name"),
                        "instruction": member.get("instruction"),
                        "verifier_evidence": _clip(member.get("verifier_evidence")),
                        "agent_messages": member.get("agent_messages"),
                        "tool_calls": member.get("tool_calls"),
                        "observations": member.get("observations"),
                    }
                    for member in representative
                ],
            }
        )
    return patterns


def passing_behaviors(cases: list[Case]) -> list[Case]:
    rows: list[Case] = []
    for case in cases:
        if case.get("outcome") != "passed":
            continue
        verification_calls = []
        for call in case.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            rendered = f"{call.get('name', '')} {call.get('arguments', '')}"
            if re.search(r"test|check|verify|lint|pytest|assert", rendered, re.I):
                verification_calls.append(call)
        rows.append(
            {
                "task_name": case.get("task_name"),
                "reward": case.get("reward"),
                "instruction": case.get("instruction"),
                "tool_sequence": _tool_sequence(case),
                "verification_calls": verification_calls,
                "final_response": (case.get("agent_messages") or [""])[-1],
            }
        )
    return rows


def reflective_records(cases: list[Case]) -> list[Case]:
    return [
        {
            "task_name": case.get("task_name"),
            "input": case.get("instruction"),
            "output": case.get("agent_messages") or case.get("raw_agent_output"),
            "reasoning_and_actions": case.get("events") or [],
            "tool_calls": case.get("tool_calls") or [],
            "tool_outputs": case.get("observations") or [],
            "feedback": {
                "outcome": case.get("outcome"),
                "reward": case.get("reward"),
                "verifier": case.get("verifier_output"),
                "exception": case.get("exception"),
            },
        }
        for case in cases
    ]


def _tool_arguments(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _ordered_behavior_events(case: Case) -> list[Case]:
    """Normalize Harbor's two ordered-event shapes without using labels."""
    normalized: list[Case] = []
    for event in case.get("trajectory_events") or case.get("events") or []:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        source = str(event.get("source") or "")
        if event_type == "message":
            if source == "agent":
                normalized.append({"type": "turn"})
            continue
        if event_type == "tool_call":
            normalized.append(
                {
                    "type": "tool_call",
                    "name": str(event.get("name") or "unknown"),
                    "arguments": event.get("arguments") or {},
                }
            )
            continue
        if event_type == "tool_result":
            normalized.append(
                {
                    "type": "tool_result",
                    "observation": str(event.get("observation") or ""),
                }
            )
            continue

        # Harbor trajectory.json steps keep calls and results together.
        if source == "agent":
            normalized.append({"type": "turn"})
        for call in event.get("tool_calls") or []:
            if isinstance(call, dict):
                normalized.append(
                    {
                        "type": "tool_call",
                        "name": str(call.get("name") or "unknown"),
                        "arguments": call.get("arguments") or {},
                    }
                )
        for observation in event.get("observations") or []:
            normalized.append({"type": "tool_result", "observation": str(observation)})
    return normalized


def _trajectory_signals(case: Case) -> dict[str, Any]:
    n_turns = 0
    n_tool_calls = 0
    n_errors = 0
    n_timeouts = 0
    tools_used: dict[str, int] = {}
    commands_run: list[str] = []
    submitted = False
    submit_value = ""
    error_messages: list[str] = []

    for event in _ordered_behavior_events(case):
        if event["type"] == "turn":
            n_turns += 1
        elif event["type"] == "tool_call":
            n_tool_calls += 1
            name = str(event.get("name") or "")
            tools_used[name] = tools_used.get(name, 0) + 1
            arguments = _tool_arguments(event.get("arguments"))
            command = arguments.get("cmd") or arguments.get("command")
            if command:
                commands_run.append(str(command)[:80])
            if name in {"submit", "task_submit"}:
                submitted = True
                submit_value = str(arguments.get("answer") or "")
        elif event["type"] == "tool_result":
            content = str(event.get("observation") or "")
            lowered = content.lower()
            if "ERROR:" in content or "error:" in lowered[:50]:
                n_errors += 1
                error_messages.append(content[:100])
            if "timed out" in lowered or "timeout" in lowered:
                n_timeouts += 1

    command_counts = Counter(commands_run)
    return {
        "n_turns": n_turns,
        "n_tool_calls": n_tool_calls,
        "n_errors": n_errors,
        "n_timeouts": n_timeouts,
        "tools_used": tools_used,
        "submitted": submitted,
        "submit_value": submit_value,
        "repeated_commands": [command for command, count in command_counts.items() if count >= 3],
        "error_snippets": error_messages[:5],
    }


def _compress_trajectory(case: Case) -> str:
    """Mirror A-Evolve's failure-focused trajectory-only compression."""
    events: list[Case] = []
    previous_command = ""
    for event in _ordered_behavior_events(case):
        if event["type"] == "tool_call":
            name = str(event.get("name") or "")
            arguments = _tool_arguments(event.get("arguments"))
            command = arguments.get("cmd") or arguments.get("command") or arguments.get("code")
            if name in {"submit", "task_submit"}:
                events.append({"type": "submit", "value": str(arguments.get("answer") or "")})
            elif command:
                previous_command = str(command)[:200]
                events.append(
                    {
                        "type": "cmd",
                        "name": name,
                        "command": previous_command,
                    }
                )
        elif event["type"] == "tool_result":
            content = str(event.get("observation") or "").strip()
            lowered = content.lower()
            is_error = (
                "ERROR:" in content
                or "error:" in lowered[:80]
                or "Traceback" in content[:200]
                or "TIMEOUT" in content.upper()[:50]
                or "timed out" in lowered[:80]
                or "No such file" in content[:100]
                or "command not found" in content[:100]
            )
            if is_error:
                events.append(
                    {
                        "type": "error",
                        "command": previous_command,
                        "output": content[:300],
                    }
                )

    commands = [event for event in events if event["type"] == "cmd"]
    errors = [event for event in events if event["type"] == "error"]
    submissions = [event for event in events if event["type"] == "submit"]
    parts = [f"Commands: {len(commands)}, Errors: {len(errors)}, Submitted: {bool(submissions)}"]
    for event in commands[:3]:
        parts.append(f"[start] {event['name']}({event['command']})")
    if errors:
        parts.append(f"\n--- Errors ({len(errors)}) ---")
        for event in errors:
            parts.append(f"  cmd: {event.get('command') or '?'}")
            parts.append(f"  err: {str(event['output'])[:200]}")

    command_counts = Counter(str(event["command"]) for event in commands)
    repeated = [(command, count) for command, count in command_counts.items() if count >= 3]
    if repeated:
        parts.append("\n--- Repeated commands ---")
        for command, count in repeated:
            parts.append(f"  {command} (x{count})")
    if commands:
        parts.append("\n--- Final commands ---")
        for event in commands[-3:]:
            parts.append(f"  {event['name']}({event['command']})")
    if submissions:
        parts.append(f"\n[submitted] {submissions[-1].get('value') or ''}")
    if case.get("outcome") in {"infra_error", "incomplete"}:
        exception = case.get("exception")
        if not isinstance(exception, dict):
            exception = {}
        exception_type = str(exception.get("type") or "RuntimeTermination")
        message = str(exception.get("message") or case.get("raw_agent_output") or "").strip()
        parts.append("\n--- Runtime termination ---")
        parts.append(f"  {exception_type}: {_clip(message, 300)}")
    return "\n".join(parts)


def trajectory_signal_records(cases: list[Case]) -> list[Case]:
    """Return the exact evidence fields exposed by A-Evolve trajectory-only mode."""
    return [
        {
            "task_id": case.get("task_name") or case.get("trial_name") or "",
            "signals": _trajectory_signals(case),
            "compressed_trajectory": _compress_trajectory(case),
        }
        for case in cases
    ]


def attach_judge_verdicts(records: list[Case], verdicts: list[Case]) -> list[Case]:
    """Attach only valid official-style proxy verdicts, preserving record order."""
    judged: list[Case] = []
    for index, record in enumerate(records):
        enriched = dict(record)
        verdict = verdicts[index] if index < len(verdicts) else {}
        score = verdict.get("score") if isinstance(verdict, dict) else None
        if isinstance(score, (int, float)) and not isinstance(score, bool) and score >= 0:
            enriched["judge_verdict"] = {
                "score": max(0, min(10, score)),
                "category": str(verdict.get("category") or "unknown"),
                "outcome": str(verdict.get("outcome") or ""),
                "failure_reason": str(verdict.get("failure_reason") or ""),
            }
        judged.append(enriched)
    return judged


def _metrics(cases: list[Case]) -> Case:
    outcomes = Counter(str(case.get("outcome") or "unknown") for case in cases)
    rewards = [float(case["reward"]) for case in cases if isinstance(case.get("reward"), (int, float))]
    return {
        "trials": len(cases),
        "outcomes": dict(sorted(outcomes.items())),
        "mean_reward": round(sum(rewards) / len(rewards), 6) if rewards else None,
        "per_task": [
            {
                "task_name": case.get("task_name"),
                "outcome": case.get("outcome"),
                "reward": case.get("reward"),
                "usage": case.get("usage"),
                "timing_s": case.get("timing_s"),
            }
            for case in cases
        ],
    }


_VARIANT_GUIDANCE = {
    "failure_patterns": "Prioritize recurring, actionable failure signatures. Preserve passing behaviors and propose a narrow edit tied to one agent mechanism.",
    "failed_traces": "Diagnose concrete capability weaknesses from failed executions and make a change that generalizes beyond one task.",
    "trace_browser": "Use filesystem tools to inspect raw traces, metrics, source, and prior generations instead of relying only on this bounded summary.",
    "trajectory_only": "Infer improvement opportunities from agent behavior alone. No pass/fail labels, rewards, verifier feedback, task text, or raw-case paths are exposed.",
    "execution_records": "Reflect across complete per-case inputs, outputs, ordered actions, tool results, verifier feedback, metrics, and history.",
    "utility_metrics": "Treat per-task reward as downstream utility and improve the editable component for average utility across tasks.",
}


def _render_selected(
    variant: str,
    metrics: Case,
    patterns: list[Case],
    passes: list[Case],
    reflections: list[Case],
    max_chars: int,
    trajectory_records: list[Case] | None = None,
) -> str:
    if variant == "trajectory_only":
        rendered = (
            "### Agent Behavior Analysis (this batch)\n\n"
            "You can ONLY see the agent's actions. You do NOT have access to actual test results.\n\n"
            "Each task includes:\n"
            "- `signals`: automated behavioral metrics (turns, errors, timeouts, submission status, loops)\n"
            "- `compressed_trajectory`: failure-focused summary (approach, errors, loops, final actions)\n"
            "- `judge_verdict`: a behavior-only LLM estimate with score (0-10), category, outcome, "
            "and failure_reason; it is not evaluator ground truth\n\n"
            "Sort tasks by judge score. Prioritize scores 0-3, inspect scores 4-6 as partial progress, "
            "and normally skip scores 7-10. Group recurring categories and failure reasons before editing.\n\n"
            "```json\n"
            f"{json.dumps(trajectory_records or [], indent=2, sort_keys=True)}\n"
            "```\n"
        )
        if len(rendered) <= max_chars:
            return rendered
        return rendered[:max_chars] + f"\n...[behavior evidence truncated {len(rendered) - max_chars} chars]...\n"

    lines = [
        "# Trace Analysis Feedback",
        "",
        f"## Trace Analyzer Variant: {variant}",
        "",
        _VARIANT_GUIDANCE[variant],
        "",
        "The full redacted evidence is under `$EVOLVE_RUN_DIR/trace_analyzer/evidence/`; use filesystem tools to inspect it when the selected view calls for raw or historical evidence.",
        "",
        "## Aggregate metrics",
        "",
        "```json",
        json.dumps(metrics, indent=2, sort_keys=True),
        "```",
    ]
    if variant == "failure_patterns":
        lines.extend(
            ["", "## Verifier-grounded failure patterns", "", "```json", json.dumps(patterns, indent=2), "```"]
        )
        lines.extend(["", "## Passing behaviors to preserve", "", "```json", json.dumps(passes, indent=2), "```"])
    elif variant == "failed_traces":
        failed_reflections = [
            record
            for record in reflections
            if (record.get("feedback") or {}).get("outcome") in {"failed", "agent_error"}
        ]
        lines.extend(
            ["", "## Detailed failed executions", "", "```json", json.dumps(failed_reflections, indent=2), "```"]
        )
    elif variant == "trace_browser":
        lines.extend(
            [
                "",
                "## Filesystem interface",
                "",
                "Inspect `raw_traces.jsonl`, `reflective_records.jsonl`, `failure_patterns.json`, and `metrics.json`. Compare these with prior generation directories under `$EVOLVE_WORKSPACE/runs/` and with the candidate source currently checked out.",
            ]
        )
    elif variant == "execution_records":
        lines.extend(["", "## Execution records", "", "```json", json.dumps(reflections, indent=2), "```"])
    elif variant == "utility_metrics":
        lines.extend(
            ["", "## Downstream utility observations", "", "```json", json.dumps(metrics["per_task"], indent=2), "```"]
        )
    rendered = "\n".join(lines) + "\n"
    if len(rendered) <= max_chars:
        return rendered
    return (
        rendered[:max_chars]
        + f"\n...[selected evidence truncated {len(rendered) - max_chars} chars; inspect files]...\n"
    )


def write_evidence_bundle(
    run_dir: Path,
    cases: list[Case],
    *,
    variant: object = "failure_patterns",
    max_chars: int = 30000,
    judge_verdicts: list[Case] | None = None,
) -> tuple[str, list[str]]:
    """Persist method-neutral evidence once and render a bounded selected view."""
    selected = normalize_variant(variant)
    root = run_dir / "trace_analyzer" / "evidence"
    records = failure_records(cases)
    patterns = cluster_failure_patterns(records)
    passes = passing_behaviors(cases)
    reflections = reflective_records(cases)
    metrics = _metrics(cases)
    trajectory_records = trajectory_signal_records(cases)
    if judge_verdicts is not None:
        trajectory_records = attach_judge_verdicts(trajectory_records, judge_verdicts)

    if selected == "trajectory_only":
        _write_json(root / "trajectory_only.json", trajectory_records)
        manifest = {
            "selected_variant": selected,
            "cases": len(trajectory_records),
            "evidence_policy": "trajectory_only",
            "ground_truth_exposed": False,
            "case_paths_exposed": False,
            "variants": {
                "trajectory_only": ["trajectory_only.json", "selected.md"],
            },
        }
        _write_json(root / "manifest.json", manifest)
        selected_md = _render_selected(
            selected,
            {},
            [],
            [],
            [],
            max_chars,
            trajectory_records=trajectory_records,
        )
        (root / "selected.md").write_text(selected_md)
        return selected_md, [
            "trace_analyzer/evidence/manifest.json",
            "trace_analyzer/evidence/trajectory_only.json",
            "trace_analyzer/evidence/selected.md",
        ]

    _write_jsonl(root / "raw_traces.jsonl", cases)
    _write_json(root / "failure_records.json", records)
    _write_json(root / "failure_patterns.json", patterns)
    _write_json(root / "passing_behaviors.json", passes)
    _write_jsonl(root / "reflective_records.jsonl", reflections)
    _write_json(root / "metrics.json", metrics)
    manifest = {
        "selected_variant": selected,
        "variants": {
            "failure_patterns": ["failure_patterns.json", "passing_behaviors.json", "metrics.json"],
            "failed_traces": ["reflective_records.jsonl", "metrics.json"],
            "trace_browser": ["raw_traces.jsonl", "metrics.json", "prior generation runs + source tree"],
            "execution_records": ["raw_traces.jsonl", "reflective_records.jsonl", "metrics.json", "history"],
            "utility_metrics": ["metrics.json", "source tree"],
        },
    }
    _write_json(root / "manifest.json", manifest)
    selected_md = _render_selected(selected, metrics, patterns, passes, reflections, max_chars)
    (root / "selected.md").write_text(selected_md)
    artifacts = [
        "trace_analyzer/evidence/manifest.json",
        "trace_analyzer/evidence/raw_traces.jsonl",
        "trace_analyzer/evidence/failure_records.json",
        "trace_analyzer/evidence/failure_patterns.json",
        "trace_analyzer/evidence/passing_behaviors.json",
        "trace_analyzer/evidence/reflective_records.jsonl",
        "trace_analyzer/evidence/metrics.json",
        "trace_analyzer/evidence/selected.md",
    ]
    return selected_md, artifacts


def _load_cases(path: Path) -> list[Case]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def _positive_int(value: object, default: int) -> int:
    try:
        return max(1, int(str(value)))
    except (TypeError, ValueError):
        return default


def _trajectory_only_cases(ctx: OperatorContext, current: list[Case]) -> list[Case]:
    """Follow the selected lineage and mirror AEvolveEngine's recent-log window."""
    history_cycles = _positive_int(ctx.config.get("history_cycles"), 2)
    maximum = _positive_int(ctx.config.get("max_observations"), 30)
    prior: list[list[Case]] = []
    parent = str(ctx.parent or "")
    rows: dict[str, dict[str, Any]] = {}
    try:
        from evolve.archive import rows_by_genid

        rows = rows_by_genid(ctx.workspace)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        rows = {}

    seen: set[str] = set()
    while parent and parent not in seen and len(prior) < history_cycles - 1:
        seen.add(parent)
        cases = _load_cases(ctx.workspace / "runs" / f"gen-{parent}" / "rollout" / "cases.json")
        if cases:
            prior.append(cases)
        row = rows.get(parent) or {}
        parent = str(row.get("parent") or "")

    combined = [case for batch in reversed(prior) for case in batch]
    combined.extend(current)
    return combined[-maximum:]


class TraceAnalyzerBase(TraceAnalyzerOperator):
    variant = "failure_patterns"

    def analyze(self, checkout: Path, ctx: OperatorContext) -> TraceAnalyzerResult:
        del checkout
        selected = normalize_variant(self.variant)
        cases_path = ctx.run_dir / "rollout" / "cases.json"
        cases = _load_cases(cases_path)
        analysis_cases = _trajectory_only_cases(ctx, cases) if selected == "trajectory_only" else cases
        max_chars = max(1, int(ctx.config.get("max_chars", 30000)))
        feedback, artifacts = write_evidence_bundle(
            ctx.run_dir,
            analysis_cases,
            variant=selected,
            max_chars=max_chars,
        )
        (ctx.run_dir / "trace_analyzer" / "feedback.md").write_text(feedback)
        return TraceAnalyzerResult(
            summary={"variant": selected, "cases": len(analysis_cases), "source": str(cases_path)},
            artifacts=["trace_analyzer/feedback.md", *artifacts],
        )
