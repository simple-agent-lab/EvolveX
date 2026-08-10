"""Analyze generated artifacts and rubric judgments without requiring a trace."""

# ruff: noqa: E402

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from evolve.frozen import sdk
from evolve.frozen.interfaces import AnalyzeOperator, AnalyzeResult, OperatorContext
from library._shared.config import config_object, reject_unknown
from library._shared.gepa import component_paths, read_json


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, {"components", "weak_score"})
    weak_score = config.get("weak_score", 2.0)
    if isinstance(weak_score, bool) or not isinstance(weak_score, (int, float)):
        raise ValueError("weak_score must be a finite number")
    normalized_score = float(weak_score)
    if not math.isfinite(normalized_score):
        raise ValueError("weak_score must be a finite number")
    return {"components": component_paths(config), "weak_score": normalized_score}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _cases(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def _judgments(case: dict[str, Any]) -> list[dict[str, Any]]:
    value = case.get("judgments")
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _diagnosis(case: dict[str, Any], weak_score: float) -> dict[str, Any]:
    judgments = _judgments(case)
    hard = [row for row in judgments if row.get("hard_failure") is True]
    weak = [
        row
        for row in judgments
        if row.get("hard_failure") is not True
        and isinstance(row.get("score"), (int, float))
        and not isinstance(row.get("score"), bool)
        and float(row["score"]) <= weak_score
    ]
    return {
        "task_id": case.get("task_name") or case.get("trial_name"),
        "outcome": case.get("outcome"),
        "artifacts": case.get("artifacts") or [],
        "hard_failures": hard,
        "weak_rubrics": weak,
        "metrics": case.get("metrics") or {},
        "feedback": case.get("feedback") or {},
    }


def _reflection(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "Inputs": case.get("inputs") or {"instruction": case.get("instruction") or ""},
        "Generated Artifacts": {
            "outputs": case.get("outputs") or {},
            "artifacts": case.get("artifacts") or [],
        },
        "Rubric Feedback": {
            "judgments": _judgments(case),
            "feedback": case.get("feedback") or {},
            "outcome": case.get("outcome"),
        },
        "Scores (Higher is Better)": case.get("metrics") or {"reward": case.get("reward")},
    }


def _feedback_text(case: dict[str, Any], limit: int = 900) -> str:
    feedback = case.get("feedback")
    if isinstance(feedback, dict):
        parts = [str(feedback.get(key) or "").strip() for key in ("message", "summary", "improvement")]
        text = " ".join(part for part in parts if part)
    else:
        text = str(feedback or "").strip()
    return text[:limit]


def _selected_report(diagnoses: list[dict[str, Any]], rubric_counts: Counter[str]) -> str:
    sections = [
        "# Artifact Rubric Analysis",
        "",
        f"Analyzed {len(diagnoses)} generated-artifact cases without requiring execution trajectories.",
        "",
        "## Highest-priority evidence",
        "",
    ]
    for diagnosis in diagnoses:
        task_id = str(diagnosis.get("task_id") or "unknown")
        failures = [*diagnosis["hard_failures"], *diagnosis["weak_rubrics"]]
        sections.extend([f"### {task_id}", ""])
        if failures:
            for row in failures:
                kind = "hard failure" if row.get("hard_failure") is True else f"score {row.get('score')}"
                detail = str(row.get("feedback") or "").strip()
                suffix = f": {detail}" if detail else ""
                sections.append(f"- `{row.get('rubric_id') or 'unknown'}` ({kind}){suffix}")
        else:
            sections.append("- No hard or weak rubric judgments.")
        feedback = str(diagnosis.get("feedback_text") or "").strip()
        if feedback:
            sections.append(f"- Judge feedback: {feedback}")
        artifact_paths = [
            str(row.get("path"))
            for row in diagnosis.get("artifacts", [])
            if isinstance(row, dict) and row.get("kind") in {"png", "svg"} and row.get("path")
        ]
        if artifact_paths:
            rendered = ", ".join(f"`{path}`" for path in artifact_paths)
            sections.append(f"- Visual artifacts: {rendered}")
        sections.append("")
    sections.extend(["## Repeated weaknesses", ""])
    sections.extend(
        [f"- `{name}`: {count} cases" for name, count in rubric_counts.most_common()]
        or ["- No repeated hard or weak rubric judgments."]
    )
    return "\n".join(sections).rstrip() + "\n"


class ArtifactRubricAnalyzer(AnalyzeOperator):
    def analyze(self, checkout: Path, ctx: OperatorContext) -> AnalyzeResult:
        del checkout
        cases = _cases(ctx.run_dir / "rollout" / "cases.json")
        if not cases:
            raise SystemExit("artifact rubric analysis requires rollout/cases.json")
        weak_score = float(ctx.config.get("weak_score", 2))
        components = component_paths(ctx.config)
        diagnoses = [{**_diagnosis(case, weak_score), "feedback_text": _feedback_text(case)} for case in cases]
        records = [_reflection(case) for case in cases]
        rubric_counts = Counter(
            str(row.get("rubric_id") or "unknown")
            for diagnosis in diagnoses
            for row in [*diagnosis["hard_failures"], *diagnosis["weak_rubrics"]]
        )

        root = ctx.run_dir / "analyze"
        evidence = root / "evidence"
        _write_json(evidence / "diagnosis.json", diagnoses)
        _write_json(evidence / "rubric_failures.json", dict(sorted(rubric_counts.items())))
        _write_json(
            evidence / "artifact_manifest.json",
            {str(case.get("task_name") or case.get("trial_name")): case.get("artifacts") or [] for case in cases},
        )
        dataset = {name: records for name in components}
        _write_json(evidence / "reflective_dataset.json", dataset)
        metrics = {
            "cases": len(cases),
            "hard_failure_cases": sum(bool(row["hard_failures"]) for row in diagnoses),
            "weak_rubric_counts": dict(sorted(rubric_counts.items())),
            "components": {name: len(records) for name in components},
        }
        _write_json(evidence / "metrics.json", metrics)
        _write_json(
            evidence / "manifest.json",
            {
                "selected_variant": "artifact_rubric",
                "source": "rollout/cases.json",
                "evidence_schema_version": 1,
                "cases": len(cases),
                "components": components,
            },
        )
        selected = _selected_report(diagnoses, rubric_counts)
        (evidence / "selected.md").write_text(selected)
        (root / "feedback.md").write_text(selected)
        return AnalyzeResult(
            summary={"variant": "artifact_rubric", **metrics},
            artifacts=[
                "analyze/feedback.md",
                "analyze/evidence/manifest.json",
                "analyze/evidence/diagnosis.json",
                "analyze/evidence/rubric_failures.json",
                "analyze/evidence/artifact_manifest.json",
                "analyze/evidence/reflective_dataset.json",
                "analyze/evidence/metrics.json",
                "analyze/evidence/selected.md",
            ],
        )


if __name__ == "__main__":
    sdk.main(ArtifactRubricAnalyzer, validate_config=validate_config)
