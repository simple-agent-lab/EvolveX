import json
from pathlib import Path

import pytest
from conftest import git, init_recipe_with_local_inputs

from evolve.config import load_config, surface_lists
from evolve.evaluation import ContractResolutionContext, resolve_evaluation_contract

EXPECTED_OPERATOR_VARIANTS = {
    "aevolve": ("greedy", "harbor", "aevolve", "hillclimb"),
    "ahe": ("ahe_latest", "evaluation_replay", "ahe", "ahe_artifact_valid"),
    "gepa": ("pareto", "harbor", "gepa", "parent_eligible"),
    "hyperagents": ("score_child_prop", "evaluation_replay", "hyperagents", "parent_eligible"),
}


@pytest.mark.parametrize(
    ("recipe", "profile", "expected_surface"),
    [
        ("aevolve", "harbor-v1", ["target/**"]),
        ("ahe", "harbor-uv-v1", ["target/**"]),
        ("gepa", "harbor-v1", ["target/**"]),
        ("hyperagents", "harbor-uv-v1", ["target/**", "operators/**"]),
    ],
)
def test_all_partner_recipes_resolve_the_same_automatic_contract_schema(
    tmp_path: Path,
    recipe: str,
    profile: str,
    expected_surface: list[str],
) -> None:
    workspace = init_recipe_with_local_inputs(tmp_path, recipe)
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
    assert evaluator["runtime"] == {"profile": profile}
    assert "candidate_runtime" not in evaluator
    assert json.loads((workspace / "evaluator/runtime-profile.json").read_text())["name"] == profile
    assert (contract.candidate_dependency_digest is not None) is profile.endswith("-uv-v1")
    assert surface_lists(workspace)[0] == expected_surface
    assert json.loads((workspace / ".evolve-components.json").read_text())["recipe"] == recipe
    assert json.loads((workspace / "evaluator/dataset.pin").read_text())["digest"]
    for kind, variant in zip(
        ("select", "rollout", "meta_agent", "gate"),
        EXPECTED_OPERATOR_VARIANTS[recipe],
        strict=True,
    ):
        provenance = (workspace / "operators" / f"{kind}.py").read_text().splitlines()[0]
        assert f"/{kind}/{variant}.py" in provenance
