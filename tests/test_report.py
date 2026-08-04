import json
from pathlib import Path

import pytest

from evolve.archive import MECHANISM_EVAL_FIELD, append_evaluation_record
from evolve.evaluation import EvaluationRecord, Outcome, TrialResult
from evolve.report import format_report


def _diagnostics() -> dict[str, object]:
    return {
        "schema_version": 1,
        "contract_id": "a" * 64,
        "purpose": "candidate",
        "expected_trials": 3,
        "observed_trials": 2,
        "scoreable_trials": 1,
        "missing_trials": 1,
        "outcome_counts": {
            "benchmark_complete": 1,
            "infrastructure_failed": 1,
            "missing": 1,
        },
        "owner_counts": {"benchmark": 1, "benchmark_agent": 1, "evaluator": 1},
        "timeouts_by_owner": {"benchmark_agent": 1},
        "failures": [
            {
                "category": "benchmark_agent_timeout",
                "owner": "benchmark_agent",
                "count": 1,
                "actionable": False,
            },
            {"category": "missing", "owner": "evaluator", "count": 1, "actionable": False},
        ],
        "retry_eligible": True,
        "contract_certified": True,
        "artifact_references": [],
    }


def _incomplete_record() -> EvaluationRecord:
    return EvaluationRecord(
        experiment_id="report-diagnostics",
        generation="1",
        candidate_commit="abc",
        purpose="candidate",
        attempt=1,
        evaluator_fingerprint="evaluator",
        task_set_hash="tasks",
        runtime_fingerprint="runtime",
        expected_trials=3,
        outcome=Outcome.INFRASTRUCTURE_FAILED,
        reason="insufficient scoreable trial evidence",
        trials=(
            TrialResult("ok", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),
            TrialResult("timeout", 0, Outcome.TIMEOUT, 0.0, "benchmark_agent"),
            TrialResult("missing", 0, Outcome.MISSING, None, "evaluator"),
        ),
        score=None,
        scoreable_trials=1,
        cost_usd=0.0,
        wall_s=1.0,
        contract_id="a" * 64,
        contract_certified=True,
        diagnostics=_diagnostics(),
    )


def test_report_separates_latest_evidence_coverage_from_best_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    append_evaluation_record(workspace, _incomplete_record())

    report = format_report(workspace)

    assert "best_score: none" in report
    assert "evidence_genid: 1" in report
    assert "expected_trials: 3" in report
    assert "observed_trials: 2" in report
    assert "scoreable_trials: 1" in report
    assert "infrastructure_failed: 1" in report
    assert "candidate_invalid: 0" in report
    assert 'timeouts_by_owner: {"benchmark_agent":1}' in report
    assert "missing_trials: 1" in report
    assert f"contract_id: {'a' * 64}" in report
    assert "contract_certified: true" in report
    assert "receipt_certified: true" in report
    assert "evaluation_complete: false" in report
    assert report.count("expected_trials:") == 1


def test_report_marks_unreceipted_diagnostics_uncertified(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    event = {
        **_incomplete_record().to_dict(),
        "event_type": "evaluation",
        "genid": "1",
        "tag": "gen/1",
        "status": "infrastructure_failed",
        "task_set_members": ["ok", "timeout", "missing"],
        "task_vector": {"schema_version": 1, "tasks": {}},
        "valid_parent": False,
        "verdict": "discard",
        "cost": {"usd": 0.0, "wall_s": 1.0},
        MECHANISM_EVAL_FIELD: True,
    }
    (workspace / "archive.jsonl").write_text(json.dumps(event) + "\n")

    report = format_report(workspace)

    assert "receipt_certified: false" in report
    assert "evaluation_complete: false" in report
