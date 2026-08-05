import json
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import (
    FIXTURE_SEEDS,
    contract_for_gen0,
    fixture_recipe_config,
    git,
    init_recipe_with_local_inputs,
)

from evolve import evaluation as evaluation_package
from evolve.workspace import InitOptions, init_workspace


def _dataset(root: Path, count: int = 10) -> Path:
    root.mkdir()
    for index in range(count):
        task = root / f"task-{index}"
        task.mkdir()
        (task / "task.toml").write_text(f'version = "1.0"\nname = "task-{index}"\n')
    return root


def _strict_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dataset = _dataset(tmp_path / "tasks")
    workspace = tmp_path / "workspace"
    config = fixture_recipe_config("hill_climb-smoke", workspace.name)
    config["target"]["seed"] = str(FIXTURE_SEEDS / "dummy")
    config["experiment"]["seed"] = 17
    config["evaluator"].update(
        {
            "dataset": str(dataset),
            "model": "openai/test-model",
            "repetitions": 2,
            "tasks_per_round": 2,
            "n_concurrent": 3,
            "max_retries": 1,
            "runtime": {"profile": "harbor-v1"},
            "agent_env": {"STEP_LIMIT": "100"},
        }
    )
    config["evaluator"].pop("k", None)
    monkeypatch.setattr("evolve.workspace.default_config", lambda _recipe, _experiment: config)
    init_workspace(InitOptions(workspace=workspace, recipe="fixture"))
    return workspace


def _context(workspace: Path, candidate_commit: str, *, generation: str = "0"):
    return evaluation_package.ContractResolutionContext(
        workspace=workspace,
        candidate_commit=candidate_commit,
        purpose="candidate",
        generation=generation,
        task_limit=None,
    )


def test_contract_resolver_derives_every_field_from_trusted_workspace_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _strict_workspace(tmp_path, monkeypatch)
    candidate_commit = git(workspace, "rev-parse", "gen/0^{commit}")
    manifest = json.loads((workspace / "evaluator/splits.json").read_text())
    expected_tasks = tuple(manifest["tasks"]["gate"][:2])

    contract = evaluation_package.resolve_evaluation_contract(_context(workspace, candidate_commit))

    assert contract.schema_version == 1
    assert contract.experiment_id == workspace.name
    assert contract.purpose == "candidate"
    assert contract.generation == "0"
    assert contract.candidate_commit == candidate_commit
    assert contract.candidate_tree == git(workspace, "rev-parse", f"{candidate_commit}^{{tree}}")
    assert contract.evaluator_tree == git(workspace, "rev-parse", "gen/0:evaluator")
    assert len(contract.evaluator_config_digest) == 64
    assert len(contract.dataset_content_digest) == 64
    assert len(contract.task_set_digest) == 64
    assert contract.task_members == expected_tasks
    assert contract.split == "gate"
    assert contract.repetitions == 2
    assert len(contract.seed_namespace) == 64
    assert [
        (trial.task_id, trial.repetition, trial.seed_supported, trial.seed)
        for trial in contract.trial_identities
    ] == [
        (task, repetition, False, None) for task in expected_tasks for repetition in range(2)
    ]
    assert contract.concurrency == 3
    profile = json.loads((workspace / "evaluator/runtime-profile.json").read_text())
    assert contract.runtime_profile == "harbor-v1"
    assert contract.runtime_profile_digest == profile["profile_digest"]
    assert contract.runtime_digest == "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert contract.candidate_dependency_digest is None
    assert contract.model_identity == {
        "agent": "target.agent:HarborAgent",
        "model": "openai/test-model",
        "route": "openai-compatible",
        "route_digest": profile["endpoint_digest"],
    }
    assert contract.retry_policy == {"max_retries": 1}
    assert contract.framework_version == "0.1.0"
    assert len(contract.contract_id) == 64

    serialized = json.dumps(contract.to_dict(), sort_keys=True)
    assert str(tmp_path) not in serialized
    assert "test-key-not-a-secret" not in serialized


def test_contract_hashes_complete_resolved_runtime_profile(strict_workspace: Path) -> None:
    contract = contract_for_gen0(strict_workspace)
    profile = json.loads(git(strict_workspace, "show", "gen/0:evaluator/runtime-profile.json"))

    assert contract.runtime_profile == profile["name"]
    assert contract.runtime_profile_digest == profile["profile_digest"]
    assert contract.runtime_digest == profile["runtime_digest"]
    assert contract.model_identity["route"] == "openai-compatible"
    assert contract.model_identity["route_digest"] == profile["endpoint_digest"]


def test_contract_mode_is_legacy_without_resolved_profile(legacy_workspace: Path) -> None:
    assert evaluation_package.evaluation_contract_mode(legacy_workspace) is evaluation_package.ContractMode.LEGACY_UNVERIFIED


@pytest.mark.parametrize("field", ["profile_digest", "endpoint_digest"])
def test_contract_rejects_tampered_resolved_profile(strict_workspace: Path, field: str) -> None:
    path = strict_workspace / "evaluator/runtime-profile.json"
    payload = json.loads(path.read_text())
    payload[field] = "0" * 64
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    git(strict_workspace, "add", "evaluator/runtime-profile.json")
    git(strict_workspace, "commit", "-m", f"tamper {field}")
    git(strict_workspace, "tag", "-f", "gen/0")

    with pytest.raises(evaluation_package.EvaluationContractResolutionError) as excinfo:
        contract_for_gen0(strict_workspace)

    assert excinfo.value.field == "runtime_profile"


def test_contract_rejects_runtime_pin_mismatch(strict_workspace: Path) -> None:
    (strict_workspace / "evaluator/runtime.pin").write_text("sha256:different-runtime\n")
    git(strict_workspace, "add", "evaluator/runtime.pin")
    git(strict_workspace, "commit", "-m", "tamper runtime pin")
    git(strict_workspace, "tag", "-f", "gen/0")

    with pytest.raises(evaluation_package.EvaluationContractResolutionError) as excinfo:
        contract_for_gen0(strict_workspace)

    assert excinfo.value.field == "runtime_digest"


def test_uv_candidate_dependency_identity_comes_from_profile(tmp_path: Path) -> None:
    workspace = init_recipe_with_local_inputs(tmp_path, "ahe")
    contract = contract_for_gen0(workspace)

    assert contract.candidate_dependency_digest is not None
    assert len(contract.candidate_dependency_digest) == 64


def test_contract_id_changes_with_candidate_tree_but_not_repeated_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _strict_workspace(tmp_path, monkeypatch)
    first_commit = git(workspace, "rev-parse", "gen/0^{commit}")
    first = evaluation_package.resolve_evaluation_contract(_context(workspace, first_commit))
    repeated = evaluation_package.resolve_evaluation_contract(_context(workspace, first_commit))
    (workspace / "target/README.md").write_text("changed candidate bytes\n")
    git(workspace, "add", "target/README.md")
    git(workspace, "commit", "-m", "candidate change")
    second_commit = git(workspace, "rev-parse", "HEAD")
    second = evaluation_package.resolve_evaluation_contract(
        _context(workspace, second_commit, generation="1")
    )

    assert repeated == first
    assert second.contract_id != first.contract_id
    assert second.candidate_tree != first.candidate_tree
    assert second.evaluator_tree == first.evaluator_tree
    assert second.dataset_content_digest == first.dataset_content_digest


def test_contract_resolution_fails_closed_without_authoritative_dataset_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    config = fixture_recipe_config("hill_climb-smoke", workspace.name)
    monkeypatch.setattr("evolve.workspace.default_config", lambda _recipe, _experiment: config)
    init_workspace(InitOptions(workspace=workspace, recipe="fixture"))
    commit = git(workspace, "rev-parse", "gen/0^{commit}")

    with pytest.raises(evaluation_package.EvaluationContractResolutionError) as excinfo:
        evaluation_package.resolve_evaluation_contract(_context(workspace, commit))

    assert excinfo.value.field == "dataset_content_digest"


def test_contract_writer_replaces_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _strict_workspace(tmp_path, monkeypatch)
    commit = git(workspace, "rev-parse", "gen/0^{commit}")
    contract = evaluation_package.resolve_evaluation_contract(_context(workspace, commit))
    output = tmp_path / "run" / "evaluation-contract.json"

    evaluation_package.write_evaluation_contract(output, contract)

    payload = json.loads(output.read_text())
    assert payload["contract_id"] == contract.contract_id
    assert not output.with_suffix(".json.tmp").exists()


def test_candidate_runtime_receipt_must_match_contract_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _strict_workspace(tmp_path, monkeypatch)
    commit = git(workspace, "rev-parse", "gen/0^{commit}")
    base = evaluation_package.resolve_evaluation_contract(_context(workspace, commit))
    contract = replace(base, candidate_dependency_digest="d" * 64)
    receipt = {
        "schema_version": 3,
        "variant": "uv",
        "contract_id": contract.contract_id,
        "candidate_commit": contract.candidate_commit,
        "candidate_dependency_digest": "d" * 64,
        "runtime_profile": contract.runtime_profile,
        "runtime_profile_digest": contract.runtime_profile_digest,
        "outcome": "ready",
    }

    assert evaluation_package.verify_candidate_runtime_receipt(contract, receipt).certified is True
    for field, value in (
        ("contract_id", "e" * 64),
        ("candidate_commit", "f" * 40),
        ("candidate_dependency_digest", "0" * 64),
        ("variant", "unknown"),
        ("runtime_profile", "other-profile"),
        ("runtime_profile_digest", "1" * 64),
    ):
        mismatch = evaluation_package.verify_candidate_runtime_receipt(contract, {**receipt, field: value})
        assert mismatch.certified is False
        assert field in mismatch.reason


def test_contract_without_candidate_runtime_requires_no_runtime_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _strict_workspace(tmp_path, monkeypatch)
    commit = git(workspace, "rev-parse", "gen/0^{commit}")
    contract = evaluation_package.resolve_evaluation_contract(_context(workspace, commit))

    assert evaluation_package.verify_candidate_runtime_receipt(contract, None).certified is True
    unexpected = evaluation_package.verify_candidate_runtime_receipt(
        contract,
        {
            "schema_version": 2,
            "variant": "uv",
            "contract_id": contract.contract_id,
            "candidate_commit": contract.candidate_commit,
            "candidate_dependency_digest": "a" * 64,
        },
    )
    assert unexpected.certified is False
    assert "unexpected" in unexpected.reason
