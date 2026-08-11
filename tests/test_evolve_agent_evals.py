import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "evals" / "skills" / "evolve-agent"

BEHAVIOR_DIMENSIONS = {
    "outer-ahe-agent": "method-and-control",
    "outer-aevolve-behavior": "method-selection",
    "outer-gepa-components": "method-selection",
    "outer-hill-control": "method-selection",
    "outer-hyper-process": "method-selection",
    "outer-driver-bounded": "control-path",
    "outer-evaluator-drift": "scientific-boundary",
    "outer-bounded-report": "reporting",
    "outer-budget-secrets": "scientific-boundary",
    "outer-lineage-conflict": "reporting",
    "workspace-manual-generation": "state-transitions",
    "workspace-stage-discovery": "state-transitions",
    "workspace-stale-admission": "state-transitions",
    "workspace-dirty-recovery": "recovery",
    "workspace-process-boundary": "process-evolution",
    "workspace-lineage-mismatch": "reporting",
    "authoring-external-context": "context-routing",
    "authoring-ambiguous-context": "context-routing",
    "authoring-informed-composition": "authoring-decisions",
    "authoring-custom-recipe": "authoring-decisions",
    "authoring-operator-gap": "operator-authoring",
    "authoring-deployment-gates": "authoring-approvals",
    "authoring-approval-invalidation": "authoring-approvals",
    "authoring-byte-only-invalidation": "authoring-approvals",
    "authoring-resume-record": "authoring-recovery",
}
INVOCATION_SKILLS = {
    "invoke-improve-agent": "evolve-agent",
    "invoke-choose-method": "evolve-agent",
    "invoke-inspect-lineage": "evolve-agent",
    "skip-one-off-bugfix": None,
    "skip-general-theory": None,
    "skip-read-only-code-review": None,
    "invoke-design-experiment": "evolve-agent",
    "invoke-author-operator": "evolve-agent",
}
HISTORICAL_BEHAVIOR_RESULT_IDS = frozenset(BEHAVIOR_DIMENSIONS) - {
    case_id for case_id in BEHAVIOR_DIMENSIONS if case_id.startswith("authoring-")
}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        assert key not in result, f"duplicate JSON key: {key}"
        result[key] = value
    return result


def _json(name: str) -> dict[str, Any]:
    payload = json.loads((EVAL_DIR / name).read_text(), object_pairs_hook=_unique_object)
    assert isinstance(payload, dict)
    return payload


def _jsonl(name: str) -> list[dict[str, Any]]:
    return [json.loads(line, object_pairs_hook=_unique_object) for line in (EVAL_DIR / name).read_text().splitlines()]


def test_behavior_eval_cases_are_unique_and_rubric_complete() -> None:
    cases = _jsonl("behavior_cases.jsonl")
    rubric = _json("rubric.json")
    ids = [str(case["id"]) for case in cases]

    assert len(ids) == len(set(ids)) == len(BEHAVIOR_DIMENSIONS)
    assert set(rubric["cases"]) == set(ids)
    assert {case["skill"] for case in cases} == {"evolve-agent"}
    assert {str(case["id"]): str(case["dimension"]) for case in cases} == BEHAVIOR_DIMENSIONS
    assert {
        "method-and-control",
        "method-selection",
        "control-path",
        "scientific-boundary",
        "reporting",
        "state-transitions",
        "recovery",
        "process-evolution",
        "context-routing",
        "authoring-decisions",
        "operator-authoring",
        "authoring-approvals",
        "authoring-recovery",
    } <= {case["dimension"] for case in cases}

    for case_id in ids:
        case_rubric = rubric["cases"][case_id]
        assert len(case_rubric["criteria"]) == 5
        assert sum(item["points"] for item in case_rubric["criteria"]) == 10
        assert case_rubric["hard_failures"]


def test_invocation_eval_has_positive_and_negative_cases() -> None:
    cases = _jsonl("invocation_cases.jsonl")
    ids = [str(case["id"]) for case in cases]

    assert len(ids) == len(set(ids)) == len(INVOCATION_SKILLS)
    expected = [case["expected_skill"] for case in cases]
    assert "evolve-agent" in expected
    assert None in expected
    assert {str(case["id"]): case["expected_skill"] for case in cases} == INVOCATION_SKILLS

    recorded = _json("current_results.json")["invocation"]
    assert recorded["cases_run"] == 0
    assert recorded["cases_available"] <= len(cases)


def test_prompt_renderer_keeps_rubric_hidden_and_separates_arms() -> None:
    script = EVAL_DIR / "render_prompt.py"
    control = subprocess.run(
        [sys.executable, str(script), "outer-ahe-agent", "--arm", "control"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    treatment = subprocess.run(
        [sys.executable, str(script), "outer-ahe-agent", "--arm", "treatment"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert control in treatment
    assert "$evolve-agent" not in control
    assert "$evolve-agent" in treatment
    assert str(ROOT / "skills" / "evolve-agent" / "SKILL.md") in treatment
    assert "rubric" not in control.lower()
    assert "hard failure" not in treatment.lower()


def test_smoke_baseline_is_traceable_to_behavior_cases() -> None:
    case_ids = {str(case["id"]) for case in _jsonl("behavior_cases.jsonl")}
    baseline = _json("baseline_results.json")
    results = baseline["cases"]

    assert {result["id"] for result in results} <= case_ids
    assert baseline["summary"]["cases_run"] == len(results)
    for result in results:
        assert result["paired_delta"] == result["treatment"]["score"] - result["control"]["score"]
        assert 0 <= result["control"]["score"] <= 10
        assert 0 <= result["treatment"]["score"] <= 10


def test_current_results_are_traceable_and_recompute_the_recorded_snapshot() -> None:
    case_ids = {str(case["id"]) for case in _jsonl("behavior_cases.jsonl")}
    results = _json("current_results.json")
    cases = results["cases"]

    result_ids = [case["id"] for case in cases]
    assert len(result_ids) == len(set(result_ids))
    assert set(result_ids) == HISTORICAL_BEHAVIOR_RESULT_IDS
    assert case_ids - set(result_ids) == {
        case_id for case_id in BEHAVIOR_DIMENSIONS if case_id.startswith("authoring-")
    }
    assert results["summary"]["behavior_cases_run"] == len(cases)
    assert results["summary"]["behavior_cases_available"] >= len(cases)
    assert all(len(case[arm]["criteria"]) == 5 for case in cases for arm in ("control", "treatment"))
    assert all(case[arm]["score"] == sum(case[arm]["criteria"]) for case in cases for arm in ("control", "treatment"))
    assert all(case["paired_delta"] == case["treatment"]["score"] - case["control"]["score"] for case in cases)

    control_scores = [case["control"]["score"] for case in cases]
    treatment_scores = [case["treatment"]["score"] for case in cases]
    control_passes = sum(case["control"]["score"] >= 8 and not case["control"]["hard_failure"] for case in cases)
    treatment_passes = sum(case["treatment"]["score"] >= 8 and not case["treatment"]["hard_failure"] for case in cases)
    summary = results["summary"]
    assert summary["control_passes"] == control_passes
    assert summary["treatment_passes"] == treatment_passes
    assert summary["control_mean_score"] == sum(control_scores) / len(cases)
    assert summary["treatment_mean_score"] == sum(treatment_scores) / len(cases)
    assert summary["mean_paired_delta"] == sum(case["paired_delta"] for case in cases) / len(cases)
