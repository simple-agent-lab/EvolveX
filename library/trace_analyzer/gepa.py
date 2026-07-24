"""Build GEPA reflective datasets from Harbor rollout cases."""

# ruff: noqa: E402

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, TraceAnalyzerOperator, TraceAnalyzerResult
from library.gepa_support import component_paths, read_json


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _clip(value: object, limit: int) -> object:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"\n...[truncated {len(value) - limit} chars]..."
    if isinstance(value, list):
        return [_clip(item, limit) for item in value]
    if isinstance(value, dict):
        return {str(key): _clip(item, limit) for key, item in value.items()}
    return value


def _component_filename(index: int, name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("._-") or "component"
    return f"{index:02d}-{stem}.json"


def reflective_record(case: dict[str, Any], field_limit: int) -> dict[str, Any]:
    reward = case.get("reward")
    score = float(reward) if isinstance(reward, (int, float)) and not isinstance(reward, bool) else 0.0
    return {
        "Inputs": {
            "task_id": case.get("task_name") or case.get("trial_name"),
            "instruction": _clip(case.get("instruction") or "", field_limit),
        },
        "Generated Outputs": {
            "agent_messages": _clip(case.get("agent_messages") or [], field_limit),
            "ordered_events": _clip(case.get("trajectory_events") or case.get("events") or [], field_limit),
            "tool_calls": _clip(case.get("tool_calls") or [], field_limit),
            "tool_results": _clip(case.get("observations") or [], field_limit),
            "raw_agent_output": _clip(case.get("raw_agent_output") or "", field_limit),
        },
        "Feedback": {
            "outcome": case.get("outcome"),
            "verifier_output": _clip(case.get("verifier_output") or "", field_limit),
            "verifier_rewards": _clip(case.get("verifier_rewards") or {}, field_limit),
            "exception": _clip(case.get("exception") or {}, field_limit),
        },
        "Scores (Higher is Better)": {"reward": score},
    }


class GepaTraceAnalyzer(TraceAnalyzerOperator):
    def analyze(self, checkout: Path, ctx: OperatorContext) -> TraceAnalyzerResult:
        del checkout
        components = component_paths(ctx.config)
        payload = read_json(ctx.run_dir / "rollout" / "cases.json")
        cases = [case for case in payload if isinstance(case, dict)] if isinstance(payload, list) else []
        maximum = max(1, int(ctx.config.get("max_cases", 32)))
        field_limit = max(1, int(ctx.config.get("field_limit", 4000)))
        usable = [case for case in cases if case.get("outcome") not in {"infra_error", "incomplete"}][:maximum]
        records = [reflective_record(case, field_limit) for case in usable]
        dataset = {name: records for name in components}
        root = ctx.run_dir / "trace_analyzer" / "evidence"
        _write_json(root / "reflective_dataset.json", dataset)
        _write_json(root / "raw_traces.json", usable)
        component_evidence: dict[str, dict[str, Any]] = {}
        component_artifacts: list[str] = []
        for index, (name, paths) in enumerate(components.items()):
            relative = Path("reflection") / _component_filename(index, name)
            _write_json(root / relative, records)
            component_evidence[name] = {
                "paths": paths,
                "records": len(records),
                "file": relative.as_posix(),
            }
            component_artifacts.append(f"trace_analyzer/evidence/{relative.as_posix()}")
        outcomes = Counter(str(case.get("outcome") or "unknown") for case in cases)
        metrics = {
            "trials": len(cases),
            "usable_trials": len(usable),
            "outcomes": dict(sorted(outcomes.items())),
            "components": {name: len(records) for name in components},
            "per_task": [
                {
                    "task_name": case.get("task_name"),
                    "outcome": case.get("outcome"),
                    "reward": case.get("reward"),
                }
                for case in cases
            ],
        }
        _write_json(root / "metrics.json", metrics)
        manifest = {
            "selected_variant": "gepa",
            "source": "rollout/cases.json",
            "components": components,
            "component_evidence": component_evidence,
            "reflective_dataset": "reflective_dataset.json",
            "excluded_outcomes": ["infra_error", "incomplete"],
        }
        _write_json(root / "manifest.json", manifest)
        selected = (
            "# GEPA Reflective Dataset\n\n"
            f"Built {len(records)} usable examples from {len(cases)} Harbor trials.\n\n"
            "Each component receives the task input, generated messages and ordered tool trajectory, "
            "verifier feedback, exception details, and reward.\n\n"
            "## Components\n\n"
            + "\n".join(
                f"- `{name}` ({len(records)} examples): {', '.join(paths)}" for name, paths in components.items()
            )
            + "\n\n## Outcomes\n\n```json\n"
            + json.dumps(metrics["outcomes"], indent=2, sort_keys=True)
            + "\n```\n"
        )
        (root / "selected.md").write_text(selected)
        (ctx.run_dir / "trace_analyzer" / "feedback.md").write_text(selected)
        artifacts = [
            "trace_analyzer/feedback.md",
            "trace_analyzer/evidence/manifest.json",
            "trace_analyzer/evidence/reflective_dataset.json",
            "trace_analyzer/evidence/raw_traces.json",
            "trace_analyzer/evidence/metrics.json",
            "trace_analyzer/evidence/selected.md",
            *component_artifacts,
        ]
        return TraceAnalyzerResult(
            summary={
                "variant": "gepa",
                "cases": len(cases),
                "usable_cases": len(usable),
                "components": list(components),
            },
            artifacts=artifacts,
        )


if __name__ == "__main__":
    sdk.main(GepaTraceAnalyzer)
