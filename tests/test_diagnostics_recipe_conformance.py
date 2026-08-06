import json
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import FIXTURE_SEEDS, git, write_locked_miniswe_seed

from evolve.archive import append_evaluation_record
from evolve.evaluation import (
    ContractResolutionContext,
    Outcome,
    TrialResult,
    classify_evaluation,
    evaluation_diagnostics,
    materialize_missing_trials,
    resolve_evaluation_contract,
)
from evolve.feedback import write_feedback_bundle
from evolve.frozen import sdk
from evolve.report import format_report
from evolve.workspace import InitOptions, init_workspace

DIAGNOSTIC_KEYS = {
    "artifact_references",
    "contract_certified",
    "contract_id",
    "expected_trials",
    "failures",
    "missing_trials",
    "observed_trials",
    "outcome_counts",
    "owner_counts",
    "purpose",
    "retry_eligible",
    "schema_version",
    "scoreable_trials",
    "timeouts_by_owner",
}


def _dataset(root: Path) -> Path:
    root.mkdir()
    for index in range(10):
        task = root / f"task-{index}"
        task.mkdir()
        (task / "task.toml").write_text(f'version = "1.0"\nname = "task-{index}"\n')
    return root


@pytest.mark.parametrize(
    ("recipe", "external_seed"),
    [("aevolve", False), ("ahe", True), ("gepa", False), ("hyperagents", True)],
)
def test_partner_recipes_share_receipt_feedback_sdk_and_report_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    recipe: str,
    external_seed: bool,
) -> None:
    dataset = _dataset(tmp_path / "tasks")
    seed = write_locked_miniswe_seed(tmp_path / "miniswe-seed") if external_seed else FIXTURE_SEEDS / "dummy"
    workspace = tmp_path / f"workspace-{recipe}"
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    init_workspace(InitOptions(workspace=workspace, recipe=recipe, seed=str(seed), dataset=str(dataset)))
    contract = resolve_evaluation_contract(
        ContractResolutionContext(
            workspace=workspace,
            candidate_commit=git(workspace, "rev-parse", "gen/0^{commit}"),
            purpose="candidate",
            generation="1",
        )
    )
    candidate_failure = TrialResult(
        contract.trial_identities[0].task_id,
        contract.trial_identities[0].repetition,
        Outcome.CANDIDATE_INVALID,
        None,
        "candidate",
        failure_category="invalid_tool_history",
    )
    trials = materialize_missing_trials(contract.trial_identities, (candidate_failure,))
    record = classify_evaluation(
        experiment_id=workspace.name,
        generation="1",
        candidate_commit=contract.candidate_commit,
        purpose="candidate",
        attempt=1,
        evaluator_fingerprint=contract.evaluator_tree,
        task_set_hash=contract.task_set_digest,
        runtime_fingerprint=contract.runtime_digest,
        expected_trials=len(contract.trial_identities),
        trials=trials,
        cost_usd=0.0,
        wall_s=1.0,
        contract_id=contract.contract_id,
        contract_certified=True,
    )
    record = replace(record, diagnostics=evaluation_diagnostics(record).to_dict())
    append_evaluation_record(workspace, record)
    run_dir = workspace / "runs" / "gen-2"
    write_feedback_bundle(workspace=workspace, run_dir=run_dir)

    sdk_payload = sdk.evaluation_diagnostics(workspace, "1")
    feedback_payload = json.loads((run_dir / "feedback" / "evaluation_diagnostics.json").read_text())[0]
    report = format_report(workspace)

    assert sdk_payload is not None
    assert set(sdk_payload) == DIAGNOSTIC_KEYS | {"receipt_certified"}
    assert set(feedback_payload["diagnostics"]) == DIAGNOSTIC_KEYS
    assert feedback_payload["diagnostics"] == {
        key: value for key, value in sdk_payload.items() if key != "receipt_certified"
    }
    failures = sdk_payload["failures"]
    assert any(failure["owner"] == "candidate" and failure["actionable"] for failure in failures)
    assert all(not failure["actionable"] for failure in failures if failure["owner"] != "candidate")
    assert "scoreable_trials: 0" in report
    assert "missing_trials:" in report
    assert "receipt_certified: true" in report
    assert sdk_payload["contract_id"] == contract.contract_id
    assert sdk_payload["contract_certified"] is True
