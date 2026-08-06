from pathlib import Path

from evolve.config import RECIPE_NAMES, load_config

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
SUPPORTED_RECIPES = {
    "aevolve",
    "ahe",
    "ahe_codex",
    "gepa",
    "gepa_local",
    "hill_climb",
    "hill_climb_codex",
    "hyperagents",
    "hyperagents_codex",
}
UV_SOURCE_RECIPES = {"ahe", "hill_climb", "hyperagents"}
MAIN_RECIPES = SUPPORTED_RECIPES - {"gepa_local"}
TERMINAL_BENCH_DATASET = "terminal-bench-2-30-v1"
CODEX_IMAGE = "evolve-meta-agent-codex:20260805-codex0145"
MINISWE_IMAGE = "evolve-meta-agent-app:20260724-tools-mswe245"


def _config(name: str) -> str:
    return (RECIPES / name / "evolve.yaml").read_text()


def _parsed_config(name: str) -> dict[str, object]:
    return load_config(RECIPES / name / "evolve.yaml")


def test_main_recipes_share_terminal_bench_and_explicit_meta_agent_images() -> None:
    for name in MAIN_RECIPES:
        config = _parsed_config(name)
        assert config["evaluator"]["dataset"] == TERMINAL_BENCH_DATASET
        expected_image = MINISWE_IMAGE if name in {"ahe", "hyperagents"} else CODEX_IMAGE
        assert config["operators"]["meta_agent"]["image"] == expected_image


def test_all_recipes_are_recipe_artifacts_only() -> None:
    recipe_names = tuple(path.name for path in sorted(RECIPES.iterdir()) if path.is_dir())
    assert set(recipe_names) == set(RECIPE_NAMES)
    assert set(RECIPE_NAMES) == SUPPORTED_RECIPES
    for name in RECIPE_NAMES:
        recipe = RECIPES / name
        assert (recipe / "evolve.yaml").is_file()
        assert (recipe / "README.md").is_file()
        assert {path.name for path in recipe.iterdir()} <= {
            "README.md",
            "dataset-manifest.json",
            "evolve.yaml",
            "notes.md",
            "prepare_dataset.py",
            "evaluator",
            "sealed",
        }
        config = _config(name)
        for section in ("experiment:", "target:", "surface:", "operators:", "evaluator:"):
            assert section in config
        top_level_sections = [line.split(":", 1)[0] for line in config.splitlines() if line and not line[0].isspace()]
        expected = ["experiment", "target", "surface", "operators"]
        if "execution_runtime:" in config:
            expected.append("execution_runtime")
        expected.append("evaluator")
        assert top_level_sections == expected


def test_supported_recipes_use_harbor_and_method_meta_agent() -> None:
    for name in SUPPORTED_RECIPES:
        config = _config(name)
        assert "engine: harbor" in config
        assert "target/**" in config
        assert "target/agent.py" not in config
        if name == "aevolve":
            assert f"dataset: {TERMINAL_BENCH_DATASET}" in config
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
        elif name == "gepa":
            assert f"dataset: {TERMINAL_BENCH_DATASET}" in config
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
        elif name == "gepa_local":
            assert "seed: builtin-local-smoke" in config
            assert "select: {variant: pareto" in config
            assert "variant: minibatch_improvement" in config
            assert "criterion: non_decreasing" in config
            assert "expose_gate_data: false" in config
            assert "agent: target.agent:HarborAgent" in config
            assert "record: {variant: gepa" in config
            assert config.count('environment: "evolve.harbor_local:LocalEnvironment"') == 3
            assert "environment: docker" not in config
            assert "image:" not in config
        elif name == "ahe":
            assert "max_generations: 10" in config
            assert f"dataset: {TERMINAL_BENCH_DATASET}" in config
            assert "seed: https://github.com/SWE-agent/mini-swe-agent.git" in config
            assert "revision: 388da74aad620a384ab47669b17c52133e30e7c3" in config
            assert "generate_lock: true" in config
            assert "rollout: {variant: parent_evaluation" in config
            assert "trace_analyzer: {variant: ahe" in config
            assert "meta_agent: {variant: ahe, runner: harbor" in config
            assert "expose_gate_data: false" in config
            assert "select: {variant: ahe_latest" in config
            assert "gate: {variant: ahe_artifact_valid" in config
            assert "max_tasks: 30" in config
            assert "max_cases" not in config
            assert "budget_usd" not in config
            assert "agent: evolve.integrations.harbor.miniswe_task_file:InstalledMiniSweAgent" in config
            assert "editable_roots: [target]" in config
            assert "max_retries: 1" in config
            assert "agent: evolve.integrations.harbor.miniswe_candidate:CandidateMiniSweAgent" in config
            assert "image: evolve-meta-agent-app:20260724-tools-mswe245" in config
            assert "task_scope: full" in config
            assert "evaluation_split: train" in config
            assert "tasks_per_round: 30" in config
            assert "repetitions: 1" in config
            assert "n_concurrent: 10" in config
            assert "\n  split:" not in config
            assert "\n  anchor:" not in config
        elif name == "ahe_codex":
            assert "max_generations: 10" in config
            assert f"dataset: {TERMINAL_BENCH_DATASET}" in config
            assert "seed: builtin-codex" in config
            assert "rollout: {variant: parent_evaluation" in config
            assert "trace_analyzer: {variant: ahe" in config
            assert "meta_agent: {variant: ahe, runner: harbor" in config
            assert "expose_gate_data: false" in config
            assert "select: {variant: ahe_latest" in config
            assert "gate: {variant: ahe_artifact_valid" in config
            assert "max_tasks: 30" in config
            assert "max_cases" not in config
            assert "budget_usd" not in config
            assert "agent: codex" in config
            assert "editable_roots: [target]" in config
            assert "max_retries: 1" in config
            assert "agent: target.agent:HarborAgent" in config
            assert "task_scope: full" in config
            assert "evaluation_split: train" in config
            assert "tasks_per_round: 30" in config
            assert "repetitions: 1" in config
            assert "n_concurrent: 5" in config
            assert "\n  split:" not in config
            assert "\n  anchor:" not in config
        elif name == "hyperagents":
            assert "max_generations: 10" in config
            assert f"dataset: {TERMINAL_BENCH_DATASET}" in config
            assert "seed: https://github.com/SWE-agent/mini-swe-agent.git" in config
            assert "revision: 388da74aad620a384ab47669b17c52133e30e7c3" in config
            assert "generate_lock: true" in config
            assert "    - operators/**" in config
            assert "    - operators/meta_agent.py" not in config
            assert "select: {variant: score_child_prop" in config
            assert "rollout: {variant: parent_evaluation" in config
            assert "trace_analyzer: {variant: trace_browser" in config
            assert "meta_agent: {variant: hyperagents" in config
            assert "expose_gate_data: false" in config
            assert "runner: harbor" in config
            assert "agent: evolve.integrations.harbor.miniswe_task_file:InstalledMiniSweAgent" in config
            assert "editable_roots: [target, operators]" in config
            assert "max_retries: 1" in config
            assert "validate: {variant: hyperagents" in config
            assert "gate: {variant: parent_eligible}" in config
            assert "record: {variant: hyperagents}" in config
            assert "image: evolve-meta-agent-app:20260724-tools-mswe245" in config
            assert "task_scope: full" in config
            assert "evaluation_split: train" in config
            assert "tasks_per_round: 30" in config
            assert "repetitions: 1" in config
            assert "n_concurrent: 10" in config
            assert "\n  split:" not in config
            assert "\n  anchor:" not in config
            assert "budget_usd" not in config
        elif name == "hyperagents_codex":
            assert "max_generations: 10" in config
            assert f"dataset: {TERMINAL_BENCH_DATASET}" in config
            assert "seed: builtin-codex" in config
            assert "    - operators/**" in config
            assert "select: {variant: score_child_prop" in config
            assert "rollout: {variant: parent_evaluation" in config
            assert "trace_analyzer: {variant: trace_browser" in config
            assert "meta_agent: {variant: hyperagents" in config
            assert "agent: codex" in config
            assert "editable_roots: [target, operators]" in config
            assert "validate: {variant: hyperagents" in config
            assert "gate: {variant: parent_eligible}" in config
            assert "record: {variant: hyperagents}" in config
            assert "agent: target.agent:HarborAgent" in config
            assert "image: evolve-meta-agent-codex:20260805-codex0145" in config
        elif name == "hill_climb_codex":
            assert f"dataset: {TERMINAL_BENCH_DATASET}" in config
            assert "seed: builtin-codex" in config
            assert "rollout: {variant: harbor" in config
            assert "trace_analyzer: {variant: failure_patterns" in config
            assert "meta_agent: {variant: hyperagents, runner: harbor" in config
            assert "agent: codex" in config
            assert "agent: target.agent:HarborAgent" in config
            assert "editable_roots: [target]" in config
            assert "image: evolve-meta-agent-codex:20260805-codex0145" in config
        else:
            assert f"dataset: {TERMINAL_BENCH_DATASET}" in config
            assert "seed: https://github.com/SWE-agent/mini-swe-agent.git" in config
            assert "rollout: {variant: harbor" in config
            assert "trace_analyzer: {variant: failure_patterns" in config
            assert "meta_agent: {variant: hyperagents, runner: harbor" in config
            assert "expose_gate_data: false" in config
            assert "agent: codex" in config
            assert "variant: noop" not in config
        assert "mutate:" not in config
        if name not in {"aevolve", "ahe_codex", "gepa", "gepa_local", "hill_climb_codex", "hyperagents_codex"}:
            assert "agent: evolve.integrations.harbor.miniswe_candidate:CandidateMiniSweAgent" in config
            assert "harbor_agent:" not in config
        assert "variant: fixed" not in config


def test_ahe_and_hyperagents_share_the_pinned_meta_agent_image() -> None:
    expected = "evolve-meta-agent-app:20260724-tools-mswe245"
    for name in ("ahe", "hyperagents"):
        assert _parsed_config(name)["operators"]["meta_agent"]["image"] == expected


def test_codex_meta_agents_use_the_preinstalled_codex_image() -> None:
    expected = "evolve-meta-agent-codex:20260805-codex0145"
    for name in ("aevolve", "ahe_codex", "gepa", "hill_climb", "hill_climb_codex", "hyperagents_codex"):
        assert _parsed_config(name)["operators"]["meta_agent"]["image"] == expected


def test_terminal_bench_method_recipes_use_full_curated_dataset() -> None:
    expected_datasets = {
        "ahe": TERMINAL_BENCH_DATASET,
        "hyperagents": TERMINAL_BENCH_DATASET,
        "hyperagents_codex": TERMINAL_BENCH_DATASET,
    }
    for name, expected_dataset in expected_datasets.items():
        recipe = _parsed_config(name)
        evaluator = recipe["evaluator"]
        assert isinstance(evaluator, dict)
        assert evaluator["dataset"] == expected_dataset
        assert "split" not in evaluator
        assert evaluator["sampling"] == "static"
        assert evaluator["tasks_per_round"] == 30
        assert evaluator["task_scope"] == "full"
        assert evaluator["evaluation_split"] == "train"
        assert evaluator["repetitions"] == 1
        assert "k" not in evaluator
        assert evaluator["n_concurrent"] == (5 if name == "hyperagents_codex" else 10)
        assert recipe["operators"]["meta_agent"]["expose_gate_data"] is False

    ahe = _parsed_config("ahe")
    assert ahe["operators"]["trace_analyzer"]["max_tasks"] == 30
    assert ahe["operators"]["trace_analyzer"]["max_concurrent"] == 10


def test_supported_uv_recipes_enable_inline_candidate_runtime_and_task_retry() -> None:
    for name in UV_SOURCE_RECIPES:
        evaluator = _parsed_config(name)["evaluator"]
        assert isinstance(evaluator, dict)
        assert evaluator["runtime"]["candidate"] == {
            "variant": "uv",
            "project": "target",
            "python": "3.12",
        }
        assert "candidate_runtime" not in evaluator
        assert evaluator["max_retries"] == 1
        assert evaluator["benchmark_timeout_is_zero"] is True


def test_shared_optimization_recipes_use_native_candidate_agent_timeout() -> None:
    for name in ("ahe", "hyperagents"):
        evaluator = _parsed_config(name)["evaluator"]
        assert isinstance(evaluator, dict)
        assert evaluator["agent_timeout_multiplier"] == 1


def test_all_explicit_recipe_retry_and_multiplier_values_are_one() -> None:
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if "retry" in key or "retries" in key or "multiplier" in key:
                    expected = 2 if key == "debugger_max_retries" else 1
                    assert item == expected, f"{key} must be {expected}, got {item!r}"
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for name in RECIPE_NAMES:
        config = _parsed_config(name)
        walk(config)
        assert "infra_repair_attempts" not in _config(name)


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
    assert contents.startswith(
        "FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90"
    )
    assert "ARG MINISWE_VERSION=2.4.5" in contents
    assert "ARG SOURCE_REVISION=unknown" in contents
    assert "WORKDIR /app" in contents
    assert "\n        python3 \\" in contents
    assert "\n        python-is-python3 \\" in contents
    assert '"mini-swe-agent==${MINISWE_VERSION}"' in contents
    assert 'io.evolve.miniswe.version="${MINISWE_VERSION}"' in contents
    assert 'org.opencontainers.image.revision="${SOURCE_REVISION}"' in contents
    assert "git config --system --add safe.directory /app/task/workspace" in contents
    for package in ("git", "jq", "python3", "python-is-python3", "ripgrep", "rsync"):
        assert f"        {package} \\" in contents
    assert 'uv tool install --python 3.13 --with fastapi --with orjson "mini-swe-agent==${MINISWE_VERSION}"' in contents
    assert "COPY uv-wrapper /root/.local/bin/uv" in contents

    wrapper = (dockerfile.parent / "uv-wrapper").read_text()
    assert '"$1" = "tool"' in wrapper
    assert '"$2" = "install"' in wrapper
    assert 'version="${EVOLVE_MINISWE_VERSION:-2.4.5}"' in wrapper
    assert 'uv-real tool install --python 3.13 --with fastapi --with orjson "mini-swe-agent==$version"' in wrapper


def test_meta_agent_required_tools_match_tier_zero_contract() -> None:
    tools = (ROOT / "containers" / "meta-agent" / "required-tools.txt").read_text().splitlines()
    assert tools == [
        "bash",
        "git",
        "curl",
        "diff",
        "file",
        "find",
        "jq",
        "patch",
        "python",
        "rg",
        "rsync",
        "sed",
        "tree",
        "uv",
        "mini-swe-agent",
    ]


def test_codex_meta_agent_image_pins_the_seed_cli_version() -> None:
    dockerfile = (ROOT / "containers" / "meta-agent-codex" / "Dockerfile").read_text()
    assert dockerfile.startswith(
        "FROM node:22-bookworm-slim@sha256:f32b81066cde10a75dbac96646099533316d94bac4150c55da1636e1f0ffdc46"
    )
    assert "FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90" in dockerfile
    assert "ARG CODEX_VERSION=0.145.0" in dockerfile
    assert 'npm install --global "@openai/codex@${CODEX_VERSION}"' in dockerfile
    assert dockerfile.count("&& codex --version") == 2
    assert "COPY --from=codex-build /usr/local/bin/node /usr/local/bin/node" in dockerfile
    assert 'io.evolve.codex.version="${CODEX_VERSION}"' in dockerfile
    assert "git config --system --add safe.directory /app/task/workspace" in dockerfile


def test_ahe_recipe_configures_reasoning_without_cost_caps() -> None:
    recipe = _parsed_config("ahe")
    assert recipe["operators"]["meta_agent"]["agent_kwargs"] == {
        "reasoning_effort": "high",
        "cost_limit": 0,
        "max_tokens": 64_000,
    }
    assert recipe["evaluator"]["agent_env"]["MINISWE_REASONING_EFFORT"] == "high"
    assert recipe["evaluator"]["agent_env"]["MINISWE_COST_LIMIT"] == "0"


def test_hyperagents_recipe_configures_reasoning_without_cost_caps() -> None:
    recipe = _parsed_config("hyperagents")
    assert recipe["operators"]["meta_agent"]["agent_kwargs"] == {
        "reasoning_effort": "high",
        "cost_limit": 0,
        "max_tokens": 64_000,
    }
    assert "budget_usd" not in recipe["experiment"]
    assert recipe["evaluator"]["agent_env"] == {
        "MINISWE_COST_LIMIT": "0",
        "MINISWE_ENV_TIMEOUT": "30",
        "MINISWE_REASONING_EFFORT": "high",
        "MINISWE_STEP_LIMIT": "100",
    }


def test_recipe_retry_and_partial_floor_defaults_remain_method_specific() -> None:
    for name in ("ahe", "hill_climb", "hill_climb_codex", "hyperagents", "hyperagents_codex"):
        evaluator = _parsed_config(name)["evaluator"]
        assert evaluator["max_retries"] == 1
        assert evaluator["partial_floor"] == 0.8


def test_harbor_evaluator_accepts_validated_runtime_concurrency_override() -> None:
    contents = (ROOT / "scaffolds/evaluators/harbor/engine.sh").read_text()
    assert "EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE" in contents
    assert "invalid EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE" in contents
