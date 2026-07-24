from pathlib import Path

from evolve.config import RECIPE_NAMES, load_config

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
REAL_RECIPES = {"aevolve", "aevolve_tbench_bridge", "ahe", "gepa", "hill_climb", "hyperagents"}
UV_SOURCE_RECIPES = {"ahe", "hill_climb", "hyperagents"}
SMOKE_RECIPES = {"hill_climb-smoke", "hyperagents-smoke"}


def _config(name: str) -> str:
    return (RECIPES / name / "evolve.yaml").read_text()


def _parsed_config(name: str) -> dict[str, object]:
    return load_config(RECIPES / name / "evolve.yaml")


def test_all_recipes_are_recipe_artifacts_only() -> None:
    recipe_names = tuple(path.name for path in sorted(RECIPES.iterdir()) if path.is_dir())
    assert set(recipe_names) == set(RECIPE_NAMES)
    assert set(RECIPE_NAMES) == REAL_RECIPES | SMOKE_RECIPES
    for name in RECIPE_NAMES:
        recipe = RECIPES / name
        assert (recipe / "evolve.yaml").is_file()
        if not name.endswith("-smoke"):
            assert (recipe / "README.md").is_file()
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
        assert "target/**" in config
        assert "target/agent.py" not in config
        if name == "aevolve":
            assert "dataset: swe-bench-lite" in config
            assert "seed: builtin-codex" in config
            assert "rollout: {variant: harbor" in config
            assert "trace_analyzer: {variant: trajectory_only" in config
            assert "trajectory_only: true" in config
            assert "expose_gate_data: false" in config
            assert "variant: aevolve" in config
            assert "runner: harbor" in config
            assert "agent: codex" in config
            assert "editable_roots: [target]" in config
            assert "evolve_prompts: true" in config
            assert "evolve_skills: true" in config
            assert "evolve_memory: false" in config
            assert "evolve_tools: false" in config
            assert "agent: target.agent:HarborAgent" in config
        elif name == "aevolve_tbench_bridge":
            parsed = _parsed_config(name)
            evaluator = parsed["evaluator"]
            assert isinstance(evaluator, dict)
            assert "max_generations: 10" in config
            assert "seed: builtin-codex" in config
            assert "harbor_agent: miniswe-source" in config
            assert "rollout:\n    variant: harbor" in config
            assert "variant: trajectory_only" in config
            assert "trajectory_only: true" in config
            assert "expose_gate_data: false" in config
            assert "variant: aevolve" in config
            assert "runner: harbor" in config
            assert "agent: codex" in config
            assert "editable_roots: [target]" in config
            assert "evolve_prompts: true" in config
            assert "evolve_skills: true" in config
            assert "evolve_memory: true" in config
            assert "evolve_tools: false" in config
            assert "agent: evolve_harbor_adapter:MiniSweSourceAgent" in config
            assert evaluator["candidate_runtime"] == {"variant": "uv", "project": "target", "python": "3.12"}
            assert evaluator["max_retries"] == 15
        elif name == "gepa":
            assert "dataset: swe-bench-lite" in config
            assert "seed: builtin-codex" in config
            assert "select: {variant: pareto" in config
            assert "rollout: {variant: harbor" in config
            assert "task_sampling: generation_shuffle" in config
            assert "variant: gepa" in config
            assert "expose_gate_data: false" in config
            assert "variant: minibatch_improvement" in config
            assert "criterion: strict" in config
            assert "runner: harbor" in config
            assert "agent: codex" in config
            assert "editable_roots: [target]" in config
            assert "agent: target.agent:HarborAgent" in config
            assert "record: {variant: gepa" in config
        elif name == "ahe":
            assert "max_generations: 10" in config
            assert "dataset: terminal-bench@2.0" in config
            assert "seed: https://github.com/SWE-agent/mini-swe-agent.git" in config
            assert "rollout: {variant: evaluation_replay" in config
            assert "trace_analyzer: {variant: ahe" in config
            assert "meta_agent: {variant: ahe, runner: harbor" in config
            assert "expose_gate_data: true" in config
            assert "select: {variant: ahe_latest" in config
            assert "gate: {variant: ahe_artifact_valid" in config
            assert "max_tasks: 90" in config
            assert "max_cases" not in config
            assert "budget_usd" not in config
            assert "agent: evolve_harbor_agent:FileTaskMiniSweAgent" in config
            assert "editable_roots: [target]" in config
            assert "max_retries: 2" in config
            assert "agent: evolve_harbor_adapter:MiniSweSourceAgent" in config
            assert "image: evolve-meta-agent-app:ubuntu-latest" in config
            assert "task_scope: full" in config
            assert "evaluation_split: train" in config
            assert "tasks_per_round: 89" in config
            assert "k: 2" in config
            assert "n_concurrent: 4" in config
            assert "\n  split:" not in config
            assert "\n  anchor:" not in config
        elif name == "hyperagents":
            assert "max_generations: 10" in config
            assert "dataset: terminal-bench@2.0" in config
            assert "seed: https://github.com/SWE-agent/mini-swe-agent.git" in config
            assert "    - operators/**" in config
            assert "    - operators/meta_agent.py" not in config
            assert "select: {variant: score_child_prop" in config
            assert "rollout: {variant: evaluation_replay" in config
            assert "trace_analyzer: {variant: trace_browser" in config
            assert "meta_agent: {variant: hyperagents" in config
            assert "expose_gate_data: true" in config
            assert "runner: harbor" in config
            assert "agent: evolve_harbor_agent:FileTaskMiniSweAgent" in config
            assert "editable_roots: [target, operators]" in config
            assert "max_retries: 2" in config
            assert "validate: {variant: hyperagents" in config
            assert "gate: {variant: parent_eligible}" in config
            assert "record: {variant: hyperagents}" in config
            assert "image: evolve-meta-agent-app:ubuntu-latest" in config
            assert "task_scope: full" in config
            assert "evaluation_split: train" in config
            assert "tasks_per_round: 89" in config
            assert "k: 1" in config
            assert "n_concurrent: 4" in config
            assert "\n  split:" not in config
            assert "\n  anchor:" not in config
            assert "budget_usd" not in config
        else:
            assert "dataset: swe-bench-lite" in config
            assert "seed: https://github.com/SWE-agent/mini-swe-agent.git" in config
            assert "rollout: {variant: harbor" in config
            assert "trace_analyzer: {variant: failure_patterns" in config
            assert "meta_agent: {variant: hyperagents, runner: harbor" in config
            assert "expose_gate_data: false" in config
            assert "agent: codex" in config
            assert "variant: noop" not in config
        assert "mutate:" not in config
        if name not in {"aevolve", "gepa"}:
            assert "agent: evolve_harbor_adapter:MiniSweSourceAgent" in config
            assert "harbor_agent: miniswe-source" in config
        assert "variant: fixed" not in config


def test_real_uv_recipes_enable_candidate_runtime_and_task_retry() -> None:
    for name in UV_SOURCE_RECIPES:
        evaluator = _parsed_config(name)["evaluator"]
        assert isinstance(evaluator, dict)
        assert evaluator["candidate_runtime"] == {"variant": "uv", "project": "target", "python": "3.12"}
        assert evaluator["max_retries"] == 1
        assert evaluator["benchmark_timeout_is_zero"] is True


def test_miniswe_method_agents_use_the_rollout_model_version() -> None:
    expected_model = "openai/gpt-5.4-2026-03-05"
    for name in ("ahe", "hyperagents"):
        config = _parsed_config(name)
        operators = config["operators"]
        assert isinstance(operators, dict)
        meta_agent = operators["meta_agent"]
        assert isinstance(meta_agent, dict)
        assert meta_agent["model"] == expected_model
        evaluator = config["evaluator"]
        assert isinstance(evaluator, dict)
        assert evaluator["model"] == expected_model


def test_meta_agent_image_provides_harbor_workspace_parent() -> None:
    dockerfile = ROOT / "containers" / "meta-agent" / "Dockerfile"
    contents = dockerfile.read_text()
    assert "WORKDIR /app" in contents
    assert "git config --system --add safe.directory /app/task/workspace" in contents
    for package in ("git", "jq", "python3", "python-is-python3", "ripgrep", "rsync"):
        assert f"        {package} \\" in contents
    assert "uv tool install --python 3.13 --with fastapi --with orjson mini-swe-agent" in contents
    assert "COPY uv-wrapper /root/.local/bin/uv" in contents

    wrapper = (dockerfile.parent / "uv-wrapper").read_text()
    assert '"$1" = "tool"' in wrapper
    assert '"$2" = "install"' in wrapper
    assert 'uv-real tool install --python 3.13 --with fastapi --with orjson "$@"' in wrapper


def test_ahe_recipe_configures_reasoning_without_cost_caps() -> None:
    recipe = _parsed_config("ahe")
    assert recipe["operators"]["meta_agent"]["agent_kwargs"] == {
        "reasoning_effort": "xhigh",
        "cost_limit": 0,
    }
    assert recipe["evaluator"]["agent_env"]["MINISWE_REASONING_EFFORT"] == "high"
    assert recipe["evaluator"]["agent_env"]["MINISWE_COST_LIMIT"] == "0"


def test_hyperagents_recipe_configures_reasoning_without_cost_caps() -> None:
    recipe = _parsed_config("hyperagents")
    assert recipe["operators"]["meta_agent"]["agent_kwargs"] == {
        "reasoning_effort": "high",
        "cost_limit": 0,
    }
    assert "budget_usd" not in recipe["experiment"]
    assert recipe["evaluator"]["agent_env"] == {
        "MINISWE_REASONING_EFFORT": "high",
        "MINISWE_COST_LIMIT": "0",
    }


def test_smoke_recipes_are_explicitly_named_and_deterministic() -> None:
    for name in SMOKE_RECIPES:
        config = _config(name)
        evaluator = _parsed_config(name)["evaluator"]
        assert isinstance(evaluator, dict)
        assert "candidate_runtime" not in evaluator
        assert "engine: harbor" in config
        assert "dataset: pass@k" in config
        assert "seed: builtin-dummy" in config
        assert "agent: evolve_harbor_adapter:MiniSweSourceAgent" in config
        assert "mutate:" not in config
        if name == "hyperagents-smoke":
            assert "    - operators/**" in config
            assert "    - operators/meta_agent.py" not in config
            assert "select: {variant: score_child_prop" in config
            assert "rollout: {variant: noop}" in config
            assert "trace_analyzer:" not in config
            assert "meta_agent: {variant: hyperagents" in config
            assert "runner: local" in config
            assert "editable_roots: [target, operators]" in config
            assert "validate: {variant: hyperagents" in config
            assert "record: {variant: hyperagents}" in config
            assert "budget_usd: 1" in config
            assert "tasks_per_round: 8" in config
        else:
            assert "rollout: {variant: failure_focused" in config
            assert "trace_analyzer:" not in config
            assert "meta_agent: {variant: hyperagents, runner: local" in config
            assert "variant: noop" not in config
        assert "variant: fixed" not in config
