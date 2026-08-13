from __future__ import annotations

import json
from pathlib import Path

from evolve.composition.recipe import resolve_builtin_recipe
from evolve.config import RECIPE_NAMES

FIXTURE = Path(__file__).parent / "fixtures" / "normalized_recipe_operator_configs.json"


def normalized_public_recipe_configs() -> dict[str, dict[str, dict[str, object]]]:
    return {
        name: {stage: binding.config for stage, binding in resolve_builtin_recipe(name).operators.items()}
        for name in RECIPE_NAMES
    }


def test_public_recipe_normalization_matches_pre_schema_contract() -> None:
    assert normalized_public_recipe_configs() == json.loads(FIXTURE.read_text())
