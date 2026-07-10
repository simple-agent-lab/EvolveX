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


def test_real_recipes_use_harbor_and_method_meta_agent() -> None:
    for name in REAL_RECIPES:
        config = _config(name)
        assert "engine: harbor" in config
        assert "dataset: swe-bench-lite" in config
        assert "seed: https://github.com/SWE-agent/mini-swe-agent.git" in config
        assert "    - target/**" in config
        assert "target/agent.py" not in config
        if name == "hyperagents":
            assert "    - operators/meta_agent.py" in config
            assert "    - operators/meta_agent.md" in config
            assert "    - operators/**" not in config
            assert "select: {variant: score_child_prop" in config
            assert "rollout: {variant: noop}" in config
            assert "meta_agent: {variant: hyperagents" in config
            assert "validate: {variant: hyperagents" in config
            assert "gate: {variant: parent_eligible}" in config
            assert "record: {variant: hyperagents}" in config
            assert "stage: {tasks: 4, proceed_if: positive}" in config
        else:
            assert "meta_agent: {variant: agent_command" in config
            assert "variant: noop" not in config
        assert "mutate:" not in config
        assert "agent: target.harbor_agent:MiniSweSourceAgent" in config
        assert "harbor_agent: miniswe-source" in config
        assert "variant: fixed" not in config
        assert "engine: docker-report" not in config
        assert "engine: reflection" not in config
        assert "engine: train-bpb" not in config


def test_smoke_recipes_are_explicitly_named_and_deterministic() -> None:
    for name in SMOKE_RECIPES:
        config = _config(name)
        assert "engine: harbor" in config
        assert "dataset: pass@k" in config
        assert "seed: builtin-dummy" in config
        assert "agent: target.harbor_agent:MiniSweSourceAgent" in config
        assert "mutate:" not in config
        if name == "hyperagents-smoke":
            assert "    - operators/meta_agent.py" in config
            assert "    - operators/meta_agent.md" in config
            assert "    - operators/**" not in config
            assert "select: {variant: score_child_prop" in config
            assert "rollout: {variant: noop}" in config
            assert "meta_agent: {variant: hyperagents" in config
            assert "validate: {variant: hyperagents" in config
            assert "record: {variant: hyperagents}" in config
            assert "budget_usd: 1" in config
            assert "tasks_per_round: 8" in config
            assert "stage: {tasks: 2, proceed_if: positive}" in config
        else:
            assert "meta_agent: {variant: agent_command" in config
            assert "variant: noop" not in config
        assert "variant: fixed" not in config
