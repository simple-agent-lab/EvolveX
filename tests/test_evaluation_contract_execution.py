import hashlib
import json
from pathlib import Path

import pytest
from conftest import FIXTURE_SEEDS, fixture_recipe_config, git, init_fixture_workspace

from evolve.evaluation import ContractResolutionContext, Outcome, resolve_evaluation_contract
from evolve.evaluation.execution import evaluate
from evolve.workspace import InitOptions, init_workspace


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
        }
    )
    config["evaluator"].pop("k", None)
    monkeypatch.setattr("evolve.workspace.default_config", lambda _recipe, _experiment: config)
    init_workspace(InitOptions(workspace=workspace, recipe="fixture"))
    return workspace


def test_evaluate_attaches_the_same_atomic_contract_to_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _strict_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("EVAL_STUB", "1")

    first = evaluate(workspace, "gen/0", "0", purpose="genesis", attempt=1)
    second = evaluate(workspace, "gen/0", "0", purpose="genesis", attempt=2)

    assert first.contract_id is not None
    assert first.contract_certified is True
    assert second.contract_id == first.contract_id
    assert first.expected_trials == 4
    assert first.task_set_hash == json.loads(
        (workspace / first.evaluation_contract["path"]).read_text()
    )["task_set_digest"]
    assert first.evaluation_contract is not None
    contract_path = workspace / first.evaluation_contract["path"]
    assert contract_path.name == "evaluation-contract.json"
    assert first.evaluation_contract["sha256"] == hashlib.sha256(contract_path.read_bytes()).hexdigest()
    assert json.loads(contract_path.read_text())["contract_id"] == first.contract_id
    contract_payload = json.loads(contract_path.read_text())
    assert [(trial.task_id, trial.trial) for trial in first.trials] == [
        (identity["task_id"], identity["repetition"])
        for identity in contract_payload["trial_identities"]
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = init_fixture_workspace(tmp_path / "legacy-workspace")
    monkeypatch.setenv("EVAL_STUB", "1")

    record = evaluate(workspace, "gen/0", "0", purpose="genesis")

    assert record.contract_id is None
    assert record.evaluation_contract is None
    assert record.contract_certified is False
    assert not list((workspace / "runs/evaluations/genesis/gen-0").glob("*/attempt-*/evaluation-contract.json"))
