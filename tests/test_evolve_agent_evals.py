import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "evals" / "skills" / "evolve-agent"


def _jsonl(name: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in (EVAL_DIR / name).read_text().splitlines()]


def test_behavior_eval_cases_are_unique_and_rubric_complete() -> None:
    cases = _jsonl("behavior_cases.jsonl")
    rubric = json.loads((EVAL_DIR / "rubric.json").read_text())
    ids = [str(case["id"]) for case in cases]

    assert len(ids) == len(set(ids)) >= 12
    assert set(rubric["cases"]) == set(ids)
    assert {case["skill"] for case in cases} == {"evolve-agent"}
    assert {
        "method-and-control",
        "method-selection",
        "control-path",
        "scientific-boundary",
        "reporting",
        "state-transitions",
        "recovery",
        "process-evolution",
    } <= {case["dimension"] for case in cases}

    for case_id in ids:
        case_rubric = rubric["cases"][case_id]
        assert len(case_rubric["criteria"]) == 5
        assert sum(item["points"] for item in case_rubric["criteria"]) == 10
        assert case_rubric["hard_failures"]


def test_invocation_eval_has_positive_and_negative_cases() -> None:
    cases = _jsonl("invocation_cases.jsonl")
    ids = [str(case["id"]) for case in cases]

    assert len(ids) == len(set(ids)) >= 6
    expected = [case["expected_skill"] for case in cases]
    assert "evolve-agent" in expected
    assert None in expected


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
    baseline = json.loads((EVAL_DIR / "baseline_results.json").read_text())
    results = baseline["cases"]

    assert {result["id"] for result in results} <= case_ids
    assert baseline["summary"]["cases_run"] == len(results)
    for result in results:
        assert result["paired_delta"] == result["treatment"]["score"] - result["control"]["score"]
        assert 0 <= result["control"]["score"] <= 10
        assert 0 <= result["treatment"]["score"] <= 10


def test_current_results_cover_and_recompute_the_full_behavior_suite() -> None:
    case_ids = {str(case["id"]) for case in _jsonl("behavior_cases.jsonl")}
    results = json.loads((EVAL_DIR / "current_results.json").read_text())
    cases = results["cases"]

    assert {case["id"] for case in cases} == case_ids
    assert results["summary"]["behavior_cases_run"] == len(cases)
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
