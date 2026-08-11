import json
import subprocess
import sys
from pathlib import Path
from statistics import median
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
    "authoring-complete-decision-packet": "authoring-decisions",
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
AUTHORING_BEHAVIOR_CASE_IDS = frozenset(
    {
        "authoring-external-context",
        "authoring-ambiguous-context",
        "authoring-informed-composition",
        "authoring-complete-decision-packet",
        "authoring-custom-recipe",
        "authoring-operator-gap",
        "authoring-deployment-gates",
        "authoring-approval-invalidation",
        "authoring-byte-only-invalidation",
        "authoring-resume-record",
    }
)
HISTORICAL_BEHAVIOR_RESULT_IDS = frozenset(
    {
        "outer-ahe-agent",
        "outer-aevolve-behavior",
        "outer-gepa-components",
        "outer-hill-control",
        "outer-hyper-process",
        "outer-driver-bounded",
        "outer-evaluator-drift",
        "outer-bounded-report",
        "outer-budget-secrets",
        "outer-lineage-conflict",
        "workspace-manual-generation",
        "workspace-stage-discovery",
        "workspace-stale-admission",
        "workspace-dirty-recovery",
        "workspace-process-boundary",
        "workspace-lineage-mismatch",
    }
)
HISTORICAL_BASELINE_RESULT_IDS = frozenset({"outer-ahe-agent", "workspace-stage-discovery"})
HISTORICAL_INVOCATION_CASE_IDS = frozenset(
    {
        "invoke-improve-agent",
        "invoke-choose-method",
        "invoke-inspect-lineage",
        "skip-one-off-bugfix",
        "skip-general-theory",
        "skip-read-only-code-review",
    }
)


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


def _passes(case: dict[str, Any], arm: str, pass_score: int) -> bool:
    result = case[arm]
    return bool(result["score"] >= pass_score and not result["hard_failure"])


def test_behavior_eval_cases_are_unique_and_rubric_complete() -> None:
    cases = _jsonl("behavior_cases.jsonl")
    rubric = _json("rubric.json")
    ids = [str(case["id"]) for case in cases]

    assert len(ids) == len(set(ids)) == len(BEHAVIOR_DIMENSIONS)
    assert set(rubric["cases"]) == set(ids)
    assert {case["skill"] for case in cases} == {"evolve-agent"}
    assert {str(case["id"]): str(case["dimension"]) for case in cases} == BEHAVIOR_DIMENSIONS
    assert {str(case["id"]) for case in cases if str(case["id"]).startswith("authoring-")} == (
        AUTHORING_BEHAVIOR_CASE_IDS
    )
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


def test_complete_decision_packet_case_jointly_scores_all_eight_fields() -> None:
    rubric = _json("rubric.json")["cases"]["authoring-complete-decision-packet"]

    assert [criterion["id"] for criterion in rubric["criteria"]] == [
        "options_and_differences",
        "recommendation_and_rationale",
        "consequences_and_reversibility",
        "unknowns",
        "explicit_selection",
    ]


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
    assert recorded["cases_available"] == len(HISTORICAL_INVOCATION_CASE_IDS)
    assert {str(case["id"]) for case in cases} - HISTORICAL_INVOCATION_CASE_IDS == {
        "invoke-design-experiment",
        "invoke-author-operator",
    }


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
    cases = baseline["cases"]
    pass_score = int(_json("rubric.json")["scoring"]["pass_score"])

    assert {case["id"] for case in cases} == HISTORICAL_BASELINE_RESULT_IDS <= case_ids
    assert all(case["paired_delta"] == case["treatment"]["score"] - case["control"]["score"] for case in cases)
    assert all(case[arm]["score"] == sum(case[arm]["criteria"]) for case in cases for arm in ("control", "treatment"))

    control_scores = [case["control"]["score"] for case in cases]
    treatment_scores = [case["treatment"]["score"] for case in cases]
    paired_deltas = [case["paired_delta"] for case in cases]
    assert baseline["summary"] == {
        "cases_run": len(cases),
        "behavior_cases_available": len(HISTORICAL_BEHAVIOR_RESULT_IDS),
        "control_pass_rate": sum(_passes(case, "control", pass_score) for case in cases) / len(cases),
        "treatment_pass_rate": sum(_passes(case, "treatment", pass_score) for case in cases) / len(cases),
        "mean_control_score": sum(control_scores) / len(cases),
        "mean_treatment_score": sum(treatment_scores) / len(cases),
        "mean_paired_delta": sum(paired_deltas) / len(cases),
        "hard_failures": sum(case[arm]["hard_failure"] for case in cases for arm in ("control", "treatment")),
    }


def test_current_results_are_traceable_and_recompute_the_recorded_snapshot() -> None:
    case_ids = {str(case["id"]) for case in _jsonl("behavior_cases.jsonl")}
    results = _json("current_results.json")
    cases = results["cases"]

    result_ids = [case["id"] for case in cases]
    assert len(result_ids) == len(set(result_ids))
    assert set(result_ids) == HISTORICAL_BEHAVIOR_RESULT_IDS
    assert case_ids - set(result_ids) == AUTHORING_BEHAVIOR_CASE_IDS
    assert all(len(case[arm]["criteria"]) == 5 for case in cases for arm in ("control", "treatment"))
    assert all(case[arm]["score"] == sum(case[arm]["criteria"]) for case in cases for arm in ("control", "treatment"))
    assert all(case["paired_delta"] == case["treatment"]["score"] - case["control"]["score"] for case in cases)

    pass_score = int(results["protocol"]["pass_score"])
    control_scores = [case["control"]["score"] for case in cases]
    treatment_scores = [case["treatment"]["score"] for case in cases]
    paired_deltas = [case["paired_delta"] for case in cases]
    control_passes = sum(_passes(case, "control", pass_score) for case in cases)
    treatment_passes = sum(_passes(case, "treatment", pass_score) for case in cases)
    assert results["summary"] == {
        "behavior_cases_run": len(cases),
        "behavior_cases_available": len(HISTORICAL_BEHAVIOR_RESULT_IDS),
        "control_passes": control_passes,
        "treatment_passes": treatment_passes,
        "control_pass_rate": control_passes / len(cases),
        "treatment_pass_rate": treatment_passes / len(cases),
        "control_mean_score": sum(control_scores) / len(cases),
        "treatment_mean_score": sum(treatment_scores) / len(cases),
        "mean_paired_delta": sum(paired_deltas) / len(cases),
        "median_paired_delta": median(paired_deltas),
        "treatment_wins": sum(delta > 0 for delta in paired_deltas),
        "ties": sum(delta == 0 for delta in paired_deltas),
        "treatment_losses": sum(delta < 0 for delta in paired_deltas),
        "control_hard_failure_cases": sum(case["control"]["hard_failure"] for case in cases),
        "treatment_hard_failure_cases": sum(case["treatment"]["hard_failure"] for case in cases),
    }
