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
    elif not calls:
        mechanism = "insufficient_environment_interaction"
        causal = "agent_behavior_likely_causal"
    elif case.get("outcome") == "agent_error":
        mechanism = "agent_runtime_failure"
        causal = "agent_behavior_or_runtime"
    elif case.get("outcome") == "infra_error":
        mechanism = "external_infrastructure"
        causal = "not_attributed_to_agent"
    else:
        mechanism = "task_strategy_or_verification"
        causal = "causality_unresolved"
    if not symptoms:
        symptoms.append("verifier rejected the final environment state")
    return mechanism, causal, symptoms


def failure_records(cases: list[Case]) -> list[Case]:
    records: list[Case] = []
    for case in cases:
        if case.get("outcome") not in {"failed", "agent_error"}:
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
        if case.get("outcome") not in {"infra_error", "incomplete"}
    ]


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
) -> str:
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
) -> tuple[str, list[str]]:
    """Persist method-neutral evidence once and render a bounded selected view."""
    selected = normalize_variant(variant)
    root = run_dir / "trace_analyzer" / "evidence"
    records = failure_records(cases)
    patterns = cluster_failure_patterns(records)
    passes = passing_behaviors(cases)
    reflections = reflective_records(cases)
    metrics = _metrics(cases)

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


class TraceAnalyzerBase(TraceAnalyzerOperator):
    variant = "failure_patterns"

    def analyze(self, checkout: Path, ctx: OperatorContext) -> TraceAnalyzerResult:
        del checkout
        selected = normalize_variant(self.variant)
        cases_path = ctx.run_dir / "rollout" / "cases.json"
        cases = _load_cases(cases_path)
        max_chars = max(1, int(ctx.config.get("max_chars", 30000)))
        feedback, artifacts = write_evidence_bundle(
            ctx.run_dir,
            cases,
            variant=selected,
            max_chars=max_chars,
        )
        (ctx.run_dir / "trace_analyzer" / "feedback.md").write_text(feedback)
        return TraceAnalyzerResult(
            summary={"variant": selected, "cases": len(cases), "source": str(cases_path)},
            artifacts=["trace_analyzer/feedback.md", *artifacts],
        )
