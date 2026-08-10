import hashlib
import json
from pathlib import Path

import pytest
from conftest import (
    FIXTURE_SEEDS,
    allow_local_runtime,
    fixture_recipe_config,
    git,
    init_recipe_with_local_inputs,
    init_workspace_from_config,
)

from evolve.evaluation import ContractResolutionContext, Outcome, resolve_evaluation_contract
from evolve.evaluation import execution as execution_module
from evolve.evaluation.contract import ReceiptVerificationResult
from evolve.evaluation.execution import evaluate
from evolve.preflight import (
    PreflightFailureCategory,
    PreflightMode,
    PreflightResultV1,
)
from evolve.runtime.uv import CandidateRuntimeResult
from evolve.workspace import InitOptions


def _strict_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dataset = tmp_path / "tasks"
    dataset.mkdir()
    for index in range(10):
        task = dataset / f"task-{index}"
        task.mkdir()
        (task / "task.toml").write_text(f'version = "1.0"\nname = "task-{index}"\n')
    workspace = tmp_path / "strict-workspace"
    config = fixture_recipe_config("hill_climb-smoke", workspace.name)
    config["target"]["seed"] = str(FIXTURE_SEEDS / "dummy")
    config["evaluator"].update(
        {
            "dataset": str(dataset),
            "repetitions": 2,
            "tasks_per_round": 2,
            "n_concurrent": 2,
            "runtime": {"proxy": {"mode": "optional", "model_endpoint": "bypass"}},
        }
    )
    config["evaluator"].pop("k", None)
    init_workspace_from_config(InitOptions(workspace=workspace), config)
    allow_local_runtime(monkeypatch)
    return workspace


def failed_preflight(
    path: Path,
    category: PreflightFailureCategory = PreflightFailureCategory.CREDENTIAL_MISSING,
) -> PreflightResultV1:
    result = PreflightResultV1.failed(
        mode=PreflightMode.ORDINARY,
        runtime_digest="a" * 64,
        endpoint_digest="b" * 64,
        checks=(),
        category=category,
        message="required credential is missing",
        receipt_path=path,
    )
    result.write()
    return result


def test_strict_evaluation_stops_before_runtime_and_trials_when_preflight_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _strict_workspace(tmp_path, monkeypatch)
    calls: list[str] = []
    preflight_call: dict[str, object] = {}

    def fail_preflight(*args, **kwargs):
        del args
        preflight_call.update(kwargs)
        preflight_call["candidate_checkout_head"] = git(Path(kwargs["candidate_checkout"]), "rev-parse", "HEAD")
        return failed_preflight(Path(kwargs["receipt_path"]))

    monkeypatch.setattr(
        execution_module,
        "run_preflight",
        fail_preflight,
    )
    monkeypatch.setattr(
        execution_module,
        "prepare_candidate_runtime",
        lambda *args, **kwargs: calls.append("runtime"),
    )
    monkeypatch.setattr(
        execution_module,
        "_run_eval_script",
        lambda *args, **kwargs: calls.append("trials"),
    )

    record = evaluate(workspace, "gen/0", "0", purpose="candidate")

    assert calls == []
    candidate_checkout = preflight_call["candidate_checkout"]
    assert isinstance(candidate_checkout, Path)
    assert candidate_checkout != workspace
    assert preflight_call["candidate_checkout_head"] == record.candidate_commit
    assert preflight_call["purpose"] == "candidate"
    assert preflight_call["task_limit"] is None
    assert record.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert record.preflight_receipt is not None
    receipt_path = workspace / record.preflight_receipt["path"]
    assert receipt_path.is_file()
    assert record.preflight_receipt["sha256"] == hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    assert record.trials
    assert all(trial.outcome is Outcome.MISSING for trial in record.trials)


def test_invalid_candidate_lock_is_actionable_candidate_owned_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = init_recipe_with_local_inputs(tmp_path, "ahe")
    monkeypatch.setattr(
        execution_module,
        "run_preflight",
        lambda *args, **kwargs: failed_preflight(
            Path(kwargs["receipt_path"]),
            PreflightFailureCategory.DEPENDENCY_LOCK_INVALID,
        ),
    )
    monkeypatch.setattr(
        execution_module,
        "prepare_candidate_runtime",
        lambda *args, **kwargs: pytest.fail("runtime preparation must not run"),
    )

    record = evaluate(workspace, "gen/0", "0", purpose="candidate")

    assert record.outcome is Outcome.CANDIDATE_INVALID
    assert record.trials
    assert all(trial.outcome is Outcome.CANDIDATE_INVALID for trial in record.trials)
    assert all(trial.owner == "candidate" for trial in record.trials)
    assert all(trial.failure_category == "dependency_lock_invalid" for trial in record.trials)
    assert record.diagnostics is not None
    assert any(failure["actionable"] for failure in record.diagnostics["failures"])


def test_invalid_candidate_runtime_is_actionable_candidate_owned_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _strict_workspace(tmp_path, monkeypatch)

    def invalid_runtime(*args, **kwargs):
        run_dir = Path(args[1])
        receipt = run_dir / "candidate-runtime.json"
        receipt.write_text('{"outcome":"candidate_invalid"}\n')
        return CandidateRuntimeResult(
            "uv",
            "target",
            outcome=Outcome.CANDIDATE_INVALID,
            reason="candidate project cannot be installed",
            receipt_path=receipt,
        )

    monkeypatch.setattr(execution_module, "prepare_candidate_runtime", invalid_runtime)
    monkeypatch.setattr(
        execution_module,
        "verify_candidate_runtime_receipt",
        lambda *args: ReceiptVerificationResult(True, "contract fields match"),
    )

    record = evaluate(workspace, "gen/0", "0", purpose="candidate")

    assert record.outcome is Outcome.CANDIDATE_INVALID
    assert record.trials
    assert all(trial.outcome is Outcome.CANDIDATE_INVALID for trial in record.trials)
    assert all(trial.owner == "candidate" for trial in record.trials)
    assert all(trial.failure_category == "candidate_runtime_invalid" for trial in record.trials)
    assert record.diagnostics is not None
    assert any(failure["actionable"] for failure in record.diagnostics["failures"])


def test_evaluate_attaches_the_same_atomic_contract_to_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _strict_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("EVAL_STUB", "1")

    first = evaluate(workspace, "gen/0", "0", purpose="genesis", attempt=1)
    second = evaluate(workspace, "gen/0", "0", purpose="genesis", attempt=2)

    assert first.contract_id is not None
    assert first.contract_certified is True
    assert second.contract_id == first.contract_id
    assert first.expected_trials == 4
    assert (
        first.task_set_hash
        == json.loads((workspace / first.evaluation_contract["path"]).read_text())["task_set_digest"]
    )
    assert first.evaluation_contract is not None
    contract_path = workspace / first.evaluation_contract["path"]
    assert contract_path.name == "evaluation-contract.json"
    assert first.evaluation_contract["sha256"] == hashlib.sha256(contract_path.read_bytes()).hexdigest()
    assert json.loads(contract_path.read_text())["contract_id"] == first.contract_id
    contract_payload = json.loads(contract_path.read_text())
    assert [(trial.task_id, trial.trial) for trial in first.trials] == [
        (identity["task_id"], identity["repetition"]) for identity in contract_payload["trial_identities"]
    ]
    assert first.diagnostics is not None
    assert first.diagnostics["observed_trials"] == 4
    assert first.diagnostics["missing_trials"] == 0
    assert second.evaluation_contract is not None
    assert second.evaluation_contract["path"] != first.evaluation_contract["path"]


def test_strict_evaluation_materializes_absent_stub_task_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _strict_workspace(tmp_path, monkeypatch)
    contract = resolve_evaluation_contract(
        ContractResolutionContext(
            workspace=workspace,
            candidate_commit="gen/0",
            purpose="candidate",
            generation="1",
        )
    )
    absent_task = contract.task_members[0]
    target = workspace / "target" / "agent.py"
    target.write_text(target.read_text() + f"\n# MISSING {absent_task}\n")
    git(workspace, "add", "target/agent.py")
    git(workspace, "commit", "-m", "candidate with missing stub evidence")
    git(workspace, "tag", "gen/1")
    monkeypatch.setenv("EVAL_STUB", "1")

    record = evaluate(workspace, "gen/1", "1", purpose="candidate")

    missing = [trial for trial in record.trials if trial.outcome is Outcome.MISSING]
    assert [(trial.task_id, trial.trial) for trial in missing] == [
        (absent_task, 0),
        (absent_task, 1),
    ]
    assert all(trial.reward is None for trial in missing)
    assert record.diagnostics is not None
    assert record.diagnostics["expected_trials"] == 4
    assert record.diagnostics["observed_trials"] == 2
    assert record.diagnostics["missing_trials"] == 2


def test_evaluate_keeps_legacy_unverified_workspace_on_explicit_compatibility_path(
    legacy_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVAL_STUB", "1")

    record = evaluate(legacy_workspace, "gen/0", "0", purpose="genesis")

    assert record.contract_id is None
    assert record.evaluation_contract is None
    assert record.contract_certified is False
    assert not list((legacy_workspace / "runs/evaluations/genesis/gen-0").glob("*/attempt-*/evaluation-contract.json"))
