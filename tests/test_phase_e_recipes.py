from pathlib import Path

from evolve.config import RECIPE_NAMES

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
REAL_RECIPES = {"hill_climb", "dgm", "ahe", "autoresearch", "hyperagents", "metaagent"}
SMOKE_RECIPES = {f"{name}-smoke" for name in REAL_RECIPES}


def _config(name: str) -> str:
    return (RECIPES / name / "evolve.yaml").read_text()


def test_all_recipes_are_recipe_artifacts_only() -> None:
    recipe_names = tuple(path.name for path in sorted(RECIPES.iterdir()) if path.is_dir())
    assert set(recipe_names) == set(RECIPE_NAMES)
    assert set(RECIPE_NAMES) == REAL_RECIPES | SMOKE_RECIPES
    for name in RECIPE_NAMES:
        recipe = RECIPES / name
        assert (recipe / "README.md").is_file()
        assert (recipe / "evolve.yaml").is_file()
        assert {path.name for path in recipe.iterdir()} <= {"README.md", "evolve.yaml", "notes.md"}
        config = _config(name)
        for section in ("experiment:", "target:", "surface:", "operators:", "evaluator:"):
            assert section in config


def test_real_recipes_use_harbor_and_real_agent_mutation() -> None:
    for name in REAL_RECIPES:
        config = _config(name)
        assert "engine: harbor" in config
        assert "mutate: {variant: agent_command" in config
        assert "agent: target.harbor_agent:MiniSweSourceAgent" in config
        assert "harbor_agent: miniswe-source" in config
        assert "variant: fixed" not in config
        assert "variant: noop" not in config
        assert "engine: docker-report" not in config
        assert "engine: reflection" not in config
        assert "engine: train-bpb" not in config


def test_smoke_recipes_are_explicitly_named_and_deterministic() -> None:
    for name in SMOKE_RECIPES:
        config = _config(name)
        assert "engine: harbor" in config
        assert "agent: target.harbor_agent:MiniSweSourceAgent" in config
        assert "mutate: {variant: fixed" in config or "mutate: {variant: noop" in config
