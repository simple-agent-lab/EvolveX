"""Select bounded current-generation evidence for Agentic Harness Engineering."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, TraceAnalyzerOperator, TraceAnalyzerResult

Case = dict[str, Any]
ARTIFACTS = [
    "trace_analyzer/feedback.md",
    "trace_analyzer/evidence/selected.md",
    "trace_analyzer/evidence/overview.json",
    "trace_analyzer/evidence/cases.jsonl",
]
COLLECTION_LIMIT = 32
MAX_NESTING = 6
EXPANSION_FACTOR = 8
TRUNCATION_KEY = "__ahe_truncated__"
_SECRET_NAME = r"[a-z0-9_-]*(?:api[_-]?key|access[_-]?token|auth(?:orization)?|secret|password)"
_SECRET_DOUBLE_QUOTED = re.compile(
    rf'(?i)\b({_SECRET_NAME})\b(["\']?)(\s*[:=]\s*)"(?:\\.|[^"\\\r\n])*"'
)
_SECRET_SINGLE_QUOTED = re.compile(
    rf"(?i)\b({_SECRET_NAME})\b([\"']?)(\s*[:=]\s*)'(?:\\.|[^'\\\r\n])*'"
)
_BASIC_AUTHORIZATION = re.compile(
    rf"(?i)\b({_SECRET_NAME})\b([\"']?)(\s*[:=]\s*)(Basic)(\s+)([^\s,;}}]+)"
)
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


def _select(cases: list[Case], maximum: int) -> list[Case]:
    failures = [case for case in cases if case.get("outcome") != "passed"]
    successes = [case for case in cases if case.get("outcome") == "passed"]
    return (failures + successes)[:maximum]


def _outcome_counts(cases: list[Case]) -> dict[str, int]:
    counts = Counter(str(case.get("outcome") or "unknown") for case in cases)
    items = [(name, count) for name, count in sorted(counts.items()) if name != TRUNCATION_KEY]
    if len(counts) <= COLLECTION_LIMIT and len(items) == len(counts):
        return dict(items)
    kept = dict(items[: COLLECTION_LIMIT - 1])
    kept[TRUNCATION_KEY] = len(counts) - len(kept)
    return kept


def _overview(cases: list[Case], selected: list[Case], error: str | None) -> Case:
    rewards = [
        float(case["reward"])
        for case in cases
        if isinstance(case.get("reward"), (int, float)) and not isinstance(case.get("reward"), bool)
    ]
    return {
        "status": "error" if error else "ok",
        "error": error,
        "observed": len(cases),
        "selected": len(selected),
        "outcomes": _outcome_counts(cases),
        "mean_reward": round(sum(rewards) / len(rewards), 6) if rewards else None,
        "cases": [
            {
                "trial_name": case.get("trial_name"),
                "task_name": case.get("task_name"),
                "outcome": case.get("outcome"),
                "reward": case.get("reward"),
            }
            for case in selected
        ],
    }


def _markdown(overview: Case, selected: list[Case]) -> str:
    lines = [
        "# AHE Trace Evidence",
        "",
        f"- Status: {overview['status']}",
        f"- Observed cases: {overview['observed']}",
        f"- Selected cases: {overview['selected']}",
        f"- Outcomes: {json.dumps(overview['outcomes'], sort_keys=True)}",
    ]
    if overview.get("error"):
        lines.append(f"- Evidence error: {overview['error']}")
    for index, case in enumerate(selected, start=1):
        lines.extend(
            [
                "",
                f"## {index}. {case.get('task_name') or case.get('trial_name') or 'unknown task'}",
                "",
                f"- Outcome: {case.get('outcome')}",
                f"- Reward: {case.get('reward')}",
                f"- Instruction: {case.get('instruction') or '(missing)'}",
                f"- Final response: {case.get('final_response') or '(missing)'}",
                f"- Verifier evidence: {case.get('verifier_output') or '(missing)'}",
                f"- Exception: {json.dumps(case.get('exception') or {}, sort_keys=True)}",
                f"- Tool calls: {json.dumps(case.get('tool_calls') or [], sort_keys=True)}",
                f"- Observations: {json.dumps(case.get('observations') or [], sort_keys=True)}",
            ]
        )
    return "\n".join(lines) + "\n"


class AheTraceAnalyzer(TraceAnalyzerOperator):
    def analyze(self, checkout: Path, ctx: OperatorContext) -> TraceAnalyzerResult:
        raw_cases, error = _load_cases(ctx.run_dir / "rollout" / "cases.json")
        field_limit = _positive_int(ctx.config.get("field_limit"), 2000)
        cases = [_normalize(case, field_limit) for case in raw_cases]
        selected = _select(cases, _positive_int(ctx.config.get("max_cases"), 8))
        overview = _overview(cases, selected, error)
        root = ctx.run_dir / "trace_analyzer"
        evidence = root / "evidence"
        rendered = _markdown(overview, selected)
        root.mkdir(parents=True, exist_ok=True)
        (root / "feedback.md").write_text(rendered)
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "selected.md").write_text(rendered)
        _write_json(evidence / "overview.json", overview)
        _write_jsonl(evidence / "cases.jsonl", selected)
        summary = {key: value for key, value in overview.items() if key != "cases"}
        return TraceAnalyzerResult(summary=summary, artifacts=ARTIFACTS)


if __name__ == "__main__":
    sdk.main(AheTraceAnalyzer)
