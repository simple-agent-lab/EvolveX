import hashlib
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
    "outer-replay-identity": "method-and-control",
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
    "authoring-script-expert-bypass": "operator-authoring",
    "authoring-deployment-gates": "authoring-approvals",
    "authoring-approval-invalidation": "authoring-approvals",
    "authoring-byte-only-invalidation": "authoring-approvals",
    "authoring-target-drift": "authoring-approvals",
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
        "authoring-script-expert-bypass",
        "authoring-deployment-gates",
        "authoring-approval-invalidation",
        "authoring-byte-only-invalidation",
        "authoring-target-drift",
        "authoring-resume-record",
    }
)
UNREPORTED_BEHAVIOR_CASE_IDS = AUTHORING_BEHAVIOR_CASE_IDS | {"outer-replay-identity"}
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


def _passes(case: dict[str, Any], arm: str, protocol: dict[str, Any]) -> bool:
    result = case[arm]
    if protocol["hard_failure_overrides_score"] and result["hard_failure"]:
        return False
    return bool(result["score"] >= int(protocol["pass_score"]))


def _case_passes(
    case_rubric: dict[str, Any],
    *,
    score: int,
    missing_fields: set[str],
    hard_failure: bool = False,
) -> bool:
    missing_required = missing_fields & set(case_rubric.get("required_fields", []))
    if missing_required and case_rubric.get("missing_required_field_is_hard_failure"):
        hard_failure = True
    return bool(score >= int(case_rubric.get("pass_score", 8)) and not hard_failure)


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
    assert rubric["required_fields"] == [
        "options",
        "differences",
        "recommendation",
        "rationale",
        "consequences",
        "reversibility",
        "unknowns",
        "explicit_selection",
    ]
    assert rubric["missing_required_field_is_hard_failure"] is True
    assert rubric["pass_score"] == 10
    for missing in ({"explicit_selection"}, {"recommendation"}, {"rationale"}):
        assert not _case_passes(rubric, score=8, missing_fields=missing)


def test_historical_aevolve_case_contract_is_unchanged() -> None:
    cases = {case["id"]: case for case in _jsonl("behavior_cases.jsonl")}
    assert cases["outer-aevolve-behavior"]["prompt"] == (
        "We want to improve a system prompt and reusable task skills. We can retain complete behavioral trajectories, "
        "but labels, rewards, and verifier feedback must remain hidden from the mutation Agent. Choose an evolution "
        "approach and describe the evidence chain and claim boundary."
    )
    assert _json("rubric.json")["cases"]["outer-aevolve-behavior"] == {
        "criteria": [
            {
                "id": "method",
                "points": 2,
                "description": "Select A-Evolve for behavioral trajectories and prompt/skill mutation.",
            },
            {
                "id": "exposure",
                "points": 2,
                "description": "Keep labels, rewards, and verifier feedback out of mutation context.",
            },
            {
                "id": "inference",
                "points": 2,
                "description": "Use inferred outcomes and failure categories as mutation guidance, not evaluation truth.",
            },
            {
                "id": "consumption",
                "points": 2,
                "description": "Verify every changed prompt or skill is actually consumed by the evaluated target and lies in the surface.",
            },
            {
                "id": "proof",
                "points": 2,
                "description": "Use the frozen evaluator and held-out evidence for outcome claims, retaining trajectories, patch, and decision.",
            },
        ],
        "hard_failures": [
            "Exposes privileged evaluator outputs to the mutator",
            "Treats an inferred verdict as the canonical score",
            "Claims evolution of a component the target does not load",
        ],
    }


def test_new_replay_target_drift_and_script_bypass_cases_are_structured() -> None:
    rubric = _json("rubric.json")["cases"]

    assert [item["id"] for item in rubric["outer-replay-identity"]["criteria"]] == [
        "parent_candidate",
        "evaluation_contract",
        "execution_identity",
        "certified_purpose",
        "fresh_child",
    ]
    assert [item["id"] for item in rubric["authoring-target-drift"]["criteria"]] == [
        "detect",
        "target_evidence",
        "source_approval",
        "architecture",
        "deployment",
    ]
    assert [item["id"] for item in rubric["authoring-script-expert-bypass"]["criteria"]] == [
        "reject",
        "no_bypass",
        "current_capability",
        "safe_option",
        "hold",
    ]


def test_custom_recipe_reruns_scoped_recipe_check_after_every_phase() -> None:
    rubric = _json("rubric.json")["cases"]["authoring-custom-recipe"]

    assert rubric["required_phase_recipe_checks"] == ["target", "evaluator", "operators"]
    assert rubric["recipe_check_proof_scope"] == ["operator_resolution", "normalization", "composition"]


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
    history = _json("historical_protocols.json")
    metadata = history["snapshots"]["baseline_results.json"]
    cases = baseline["cases"]
    scoring = metadata["scoring"]

    assert history["version"] == 1
    assert set(history["snapshots"]) == {"baseline_results.json"}
    assert metadata["snapshot_sha256"] == hashlib.sha256((EVAL_DIR / "baseline_results.json").read_bytes()).hexdigest()
    assert metadata["behavior_case_ids"] == sorted(HISTORICAL_BEHAVIOR_RESULT_IDS)
    assert metadata["result_case_ids"] == sorted(HISTORICAL_BASELINE_RESULT_IDS)
    assert metadata["scoring"] == {"pass_score": 8, "hard_failure_overrides_score": True}
    assert {case["id"] for case in cases} == set(metadata["result_case_ids"]) <= case_ids
    assert all(case["paired_delta"] == case["treatment"]["score"] - case["control"]["score"] for case in cases)
    assert all(case[arm]["score"] == sum(case[arm]["criteria"]) for case in cases for arm in ("control", "treatment"))

    control_scores = [case["control"]["score"] for case in cases]
    treatment_scores = [case["treatment"]["score"] for case in cases]
    paired_deltas = [case["paired_delta"] for case in cases]
    assert baseline["summary"] == {
        "cases_run": len(cases),
        "behavior_cases_available": len(HISTORICAL_BEHAVIOR_RESULT_IDS),
        "control_pass_rate": sum(_passes(case, "control", scoring) for case in cases) / len(cases),
        "treatment_pass_rate": sum(_passes(case, "treatment", scoring) for case in cases) / len(cases),
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
    assert case_ids - set(result_ids) == UNREPORTED_BEHAVIOR_CASE_IDS
    assert all(len(case[arm]["criteria"]) == 5 for case in cases for arm in ("control", "treatment"))
    assert all(case[arm]["score"] == sum(case[arm]["criteria"]) for case in cases for arm in ("control", "treatment"))
    assert all(case["paired_delta"] == case["treatment"]["score"] - case["control"]["score"] for case in cases)

    protocol = results["protocol"]
    control_scores = [case["control"]["score"] for case in cases]
    treatment_scores = [case["treatment"]["score"] for case in cases]
    paired_deltas = [case["paired_delta"] for case in cases]
    control_passes = sum(_passes(case, "control", protocol) for case in cases)
    treatment_passes = sum(_passes(case, "treatment", protocol) for case in cases)
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
