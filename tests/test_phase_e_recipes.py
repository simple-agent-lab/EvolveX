from pathlib import Path

from evolve.config import RECIPE_NAMES

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"


def test_all_recipes_are_recipe_artifacts_only() -> None:
    recipe_names = tuple(path.name for path in sorted(RECIPES.iterdir()) if path.is_dir())
    assert set(recipe_names) == set(RECIPE_NAMES)
    for name in RECIPE_NAMES:
        recipe = RECIPES / name
        assert (recipe / "README.md").is_file()
        assert (recipe / "evolve.yaml").is_file()
        assert {path.name for path in recipe.iterdir()} <= {"README.md", "evolve.yaml", "notes.md"}
        config = (recipe / "evolve.yaml").read_text()
        for section in ("experiment:", "target:", "surface:", "operators:", "evaluator:"):
            assert section in config
