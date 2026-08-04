import json
from pathlib import Path

import pytest
from conftest import FIXTURE_SEEDS, git, write_locked_miniswe_seed

from evolve.config import load_config, surface_lists
from evolve.evaluation import ContractResolutionContext, resolve_evaluation_contract
from evolve.workspace import InitOptions, init_workspace


def _dataset(root: Path) -> Path:
    root.mkdir()
    for index in range(10):
        task = root / f"task-{index}"
        task.mkdir()
        (task / "task.toml").write_text(f'version = "1.0"\nname = "task-{index}"\n')
    return root


@pytest.mark.parametrize(
    ("recipe", "uses_candidate_runtime", "expected_surface"),
    [
        ("aevolve", False, ["target/**"]),
        ("ahe", True, ["target/**"]),
        ("gepa", False, ["target/**"]),
        ("hyperagents", True, ["target/**", "operators/**"]),
    ],
)
def test_all_partner_recipes_resolve_the_same_automatic_contract_schema(
    tmp_path: Path,
    recipe: str,
    uses_candidate_runtime: bool,
    expected_surface: list[str],
) -> None:
    dataset = _dataset(tmp_path / "tasks")
    seed = (
        write_locked_miniswe_seed(tmp_path / "miniswe-seed")
        if uses_candidate_runtime
        else FIXTURE_SEEDS / "dummy"
    )
    workspace = tmp_path / f"workspace-{recipe}"

    init_workspace(
        InitOptions(
            workspace=workspace,
            recipe=recipe,
            seed=str(seed),
            dataset=str(dataset),
        )
    )
    config = load_config(workspace / "evolve.yaml")
    evaluator = config["evaluator"]
    commit = git(workspace, "rev-parse", "gen/0^{commit}")
    contract = resolve_evaluation_contract(
        ContractResolutionContext(
            workspace=workspace,
            candidate_commit=commit,
            purpose="candidate",
            generation="0",
        )
    )

    assert evaluator["repetitions"] == 1
    assert "k" not in evaluator
    assert contract.schema_version == 1
    assert contract.repetitions == 1
    assert len(contract.trial_identities) == len(contract.task_members)
    assert all(trial.repetition == 0 for trial in contract.trial_identities)
    assert (contract.candidate_dependency_digest is not None) is uses_candidate_runtime
    assert surface_lists(workspace)[0] == expected_surface
    assert json.loads((workspace / ".evolve-components.json").read_text())["recipe"] == recipe
    assert json.loads((workspace / "evaluator/dataset.pin").read_text())["digest"]
