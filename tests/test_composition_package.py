from evolve.composition import ResolvedRecipe, resolve_builtin_recipe
from evolve.composition.catalog import discover_operators
from evolve.composition.cli import recipe_check_payload


def test_composition_package_exposes_resolution_catalog_and_cli_payload() -> None:
    resolved = resolve_builtin_recipe("hill_climb")

    assert isinstance(resolved, ResolvedRecipe)
    assert resolved.operators["mutate"].name == "hyperagents"
    assert ("mutate", "hyperagents") in discover_operators()
    assert recipe_check_payload(resolved)["name"] == "hill_climb"
