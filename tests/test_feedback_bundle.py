import json
from pathlib import Path

import pytest

from evolve.archive import append_evaluation_record
from evolve.evaluation import EvaluationRecord, Outcome, TrialResult
from evolve.feedback import write_feedback_bundle


def _diagnostics(generation: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "contract_id": generation.zfill(64),
        "purpose": "candidate",
        "expected_trials": 1,
        "observed_trials": 1,
        "scoreable_trials": 0,
        "missing_trials": 0,
        "outcome_counts": {"infrastructure_failed": 1},
        "owner_counts": {"evaluator": 1},
        "timeouts_by_owner": {},
        "failures": [
            {
                "category": "verifier_dependency_download",
                "owner": "evaluator",
                "count": 1,
                "actionable": False,
            }
        ],
        "retry_eligible": True,
        "contract_certified": True,
        "artifact_references": [],
    }


def _record(generation: str) -> EvaluationRecord:
    return EvaluationRecord(
        experiment_id="feedback-diagnostics",
        generation=generation,
        candidate_commit=f"commit-{generation}",
        purpose="candidate",
        attempt=1,
        evaluator_fingerprint="evaluator",
        task_set_hash="tasks",
        runtime_fingerprint="runtime",
        expected_trials=1,
        outcome=Outcome.INFRASTRUCTURE_FAILED,
        reason="infrastructure failed",
        trials=(
            TrialResult(
                "task",
                0,
                Outcome.INFRASTRUCTURE_FAILED,
                None,
                "evaluator",
                exception_message="OPENAI_API_KEY=must-not-enter-feedback",
                failure_category="verifier_dependency_download",
            ),
        ),
        score=None,
        cost_usd=0.0,
        wall_s=1.0,
        diagnostics=_diagnostics(generation),
    )


def test_feedback_bundle_exposes_only_recent_frozen_safe_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    append_evaluation_record(workspace, _record("1"))
    append_evaluation_record(workspace, _record("2"))
    run_dir = workspace / "runs" / "gen-3"

    manifest = write_feedback_bundle(workspace=workspace, run_dir=run_dir, history_k=1)

    path = run_dir / "feedback" / "evaluation_diagnostics.json"
    assert json.loads(path.read_text()) == [
        {
            "diagnostics": _diagnostics("2"),
            "genid": "2",
            "receipt_certified": True,
        }
    ]
    assert "must-not-enter-feedback" not in path.read_text()
    assert "feedback/evaluation_diagnostics.json" in manifest
    assert "[evaluation diagnostics](evaluation_diagnostics.json)" in (
        run_dir / "feedback" / "index.md"
    ).read_text()
