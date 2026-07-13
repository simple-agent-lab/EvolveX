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
        assert {path.name for path in recipe.iterdir()} <= {
            "README.md",
            "evolve.yaml",
            "notes.md",
            "evaluator",
            "sealed",
        }
        config = _config(name)
        for section in ("experiment:", "target:", "surface:", "operators:", "evaluator:"):
            assert section in config
        top_level_sections = [line.split(":", 1)[0] for line in config.splitlines() if line and not line[0].isspace()]
        assert top_level_sections == ["experiment", "target", "surface", "operators", "evaluator"]


def test_real_recipes_use_harbor_and_method_meta_agent() -> None:
    for name in REAL_RECIPES:
        config = _config(name)
        assert "engine: harbor" in config
        assert "dataset: swebenchpro@1.0" in config if name == "ahe" else "dataset: swe-bench-lite" in config
        assert "seed: https://github.com/SWE-agent/mini-swe-agent.git" in config
        assert "target/**" in config
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
        elif name == "ahe":
            assert "variant: ahe_evidence_editor" in config
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
        elif name == "ahe-smoke":
            assert "variant: ahe_evidence_editor" in config
            assert "variant: noop" not in config
        else:
            assert "meta_agent: {variant: agent_command" in config
            assert "variant: noop" not in config
        assert "variant: fixed" not in config


def test_ahe_recipe_selects_the_method_faithful_variants_and_fixed_training_set() -> None:
    ahe = _config("ahe")
    hill_climb = _config("hill_climb")

    assert "variant: ahe_latest" in ahe
    assert "variant: ahe_trace_analysis" in ahe
    assert "variant: ahe_evidence_editor" in ahe
    assert "variant: ahe_artifact_valid" in ahe
    assert "variant: ahe_manifest" in ahe
    assert "dataset: swebenchpro@1.0" in ahe
    assert "dataset_mode: registry" in ahe
    assert "task_file: evaluator/tasks/train-30.txt" in ahe
    assert "tasks_per_round: 30" in ahe
    assert "k: 2" in ahe
    assert "n_concurrent: 5" in ahe
    assert "debugger: {workers: 5, command: null, attempts: 3}" in ahe
    assert "controls: {successful: 3, rotation_seed: 0}" in ahe
    assert "target/harbor_agent.py" in ahe
    assert "ahe_" not in hill_climb
    assert "ahe_evolve.md" not in hill_climb
    assert "ahe_debugger" not in hill_climb


def test_ahe_smoke_recipe_selects_the_method_faithful_variants() -> None:
    smoke = _config("ahe-smoke")

    assert "variant: ahe_latest" in smoke
    assert "variant: ahe_trace_analysis" in smoke
    assert "variant: ahe_evidence_editor" in smoke
    assert "variant: ahe_artifact_valid" in smoke
    assert "variant: ahe_manifest" in smoke
    assert "seed: builtin-dummy" in smoke
    assert "dataset: pass@k" in smoke
    assert "task_file:" not in smoke
