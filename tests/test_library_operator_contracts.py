from pathlib import Path

import pytest

from evolve.composition import resolve_recipe
from evolve.composition.catalog import (
    LibraryOperator,
    OperatorLibraryError,
    describe_operator,
    discover_operators,
    resolve_operator,
    validate_operator_config,
)

ROOT = Path(__file__).resolve().parents[1]


def repository_recipe_paths() -> list[Path]:
    recipe_paths = sorted((ROOT / "recipes").glob("*/evolve.yaml"))
    recipe_paths += sorted((ROOT / "tests" / "fixtures" / "recipes").glob("*/evolve.yaml"))
    recipe_paths.append(ROOT / "evals" / "skills" / "make-paper-poster" / "recipe" / "evolve.yaml")
    return recipe_paths


def test_analyze_catalog_contains_only_supported_strategies() -> None:
    names = {name for stage, name in discover_operators() if stage == "analyze"}

    assert names == {
        "ahe",
        "artifact_rubric",
        "failure_patterns",
        "gepa",
        "trace_browser",
        "trajectory_only",
    }


@pytest.mark.parametrize("operator", discover_operators().values(), ids=lambda item: item.identity)
def test_every_library_operator_describes_and_validates(operator: LibraryOperator) -> None:
    description = describe_operator(operator)
    assert description["stage"] == operator.stage
    assert isinstance(description["description"], str) and description["description"].strip()
    assert description["config"]["type"] == "object"
    assert description["config"]["additionalProperties"] is False


@pytest.mark.parametrize("name", ["aevolve", "ahe", "gepa", "hyperagents"])
def test_mutate_validators_normalize_command_as_a_strict_string(name: str) -> None:
    operator = resolve_operator("mutate", name)
    base = {"components": {"prompt": "target/prompt.md"}} if name == "gepa" else {}

    normalized = validate_operator_config(
        operator,
        {**base, "runner": "local", "command": "printf accepted"},
    )

    assert normalized["command"] == "printf accepted"
    with pytest.raises(OperatorLibraryError, match="command: expected non-empty string"):
        validate_operator_config(
            operator,
            {**base, "runner": "local", "command": ["printf", "rejected"]},
        )


@pytest.mark.parametrize("name", ["aevolve", "ahe", "gepa", "hyperagents"])
def test_mutate_operators_share_runner_normalization(name: str) -> None:
    operator_config: dict[str, object] = {
        "runner": "harbor",
        "command": "printf accepted",
        "environment_kwargs": {"network": "host"},
        "agent_kwargs": {"reasoning": "high"},
        "agent_env": {"TOKEN": "configured"},
    }
    if name == "gepa":
        operator_config["components"] = {"prompt": "target/prompt.md"}

    normalized = validate_operator_config(resolve_operator("mutate", name), operator_config)

    assert normalized["runner"] == "harbor"
    assert normalized["command"] == "printf accepted"
    assert normalized["environment_kwargs"] == {"network": "host"}
    assert normalized["agent_kwargs"] == {"reasoning": "high"}
    assert normalized["agent_env"] == {"TOKEN": "configured"}


@pytest.mark.parametrize("recipe_path", repository_recipe_paths(), ids=lambda path: path.parent.name)
def test_every_recipe_selected_config_is_accepted(recipe_path: Path) -> None:
    resolved = resolve_recipe(recipe_path)

    assert resolved.operators
    assert all(isinstance(binding.config, dict) for binding in resolved.operators.values())


@pytest.mark.parametrize(
    ("stage", "name", "config", "expected"),
    [
        ("select", "greedy", {}, {"seed": 0}),
        ("gate", "hillclimb", {}, {"strict": False}),
        (
            "analyze",
            "trace_browser",
            {"history_cycles": 4, "max_observations": 12, "max_chars": 900},
            {"history_cycles": 4, "max_observations": 12, "max_chars": 900},
        ),
        (
            "rollout",
            "parent_evaluation",
            {"field_limit": 1200, "pass_threshold": 0.5},
            {"field_limit": 1200, "pass_threshold": 0.5},
        ),
        (
            "rollout",
            "harbor",
            {
                "budget_tasks": 3,
                "task_sampling": "generation_shuffle",
                "n_concurrent": 2,
                "agent_setup_timeout_multiplier": 2,
                "agent_timeout_multiplier": 1.5,
                "verifier_timeout_multiplier": 2.5,
                "max_retries": 1,
                "field_limit": 900,
                "pass_threshold": 0.75,
                "environment": "provider.Environment",
                "environment_kwargs": {"provider_option": {"nested": True}},
                "agent": "provider.Agent",
                "agent_env": {"CUSTOM": {"provider_value": 7}},
                "model": "provider/model",
                "include_task_name": "task-*",
                "jobs_dir": "runs/jobs",
                "path": "tasks",
                "split": "train",
                "task_names": ["task-a", "task-b"],
                "reuse_completed": True,
                "seed": -4,
            },
            {
                "budget_tasks": 3,
                "task_sampling": "generation_shuffle",
                "n_concurrent": 2,
                "agent_setup_timeout_multiplier": 2.0,
                "agent_timeout_multiplier": 1.5,
                "verifier_timeout_multiplier": 2.5,
                "max_retries": 1,
                "field_limit": 900,
                "pass_threshold": 0.75,
                "environment": "provider.Environment",
                "environment_kwargs": {"provider_option": {"nested": True}},
                "agent": "provider.Agent",
                "agent_env": {"CUSTOM": {"provider_value": 7}},
                "model": "provider/model",
                "include_task_name": "task-*",
                "jobs_dir": "runs/jobs",
                "path": "tasks",
                "split": "train",
                "task_names": ["task-a", "task-b"],
                "reuse_completed": True,
                "seed": -4,
            },
        ),
        (
            "analyze",
            "trajectory_only",
            {
                "judge_agent_kwargs": {"provider": {"reasoning": "high"}},
                "judge_agent_env": {"AUTH": {"source": "provider"}},
                "agent_kwargs": {"nested": [1, 2]},
            },
            {
                "history_cycles": 2,
                "max_observations": 30,
                "max_chars": 30000,
                "judge_max_concurrent": 4,
                "judge_retry_attempts": 3,
                "judge_timeout_s": 600.0,
                "judge_inherit_openai_credentials": False,
                "pass_threshold": 1.0,
                "judge_agent_kwargs": {"provider": {"reasoning": "high"}},
                "judge_agent_env": {"AUTH": {"source": "provider"}},
                "agent_kwargs": {"nested": [1, 2]},
            },
        ),
        (
            "analyze",
            "ahe",
            {"debugger": {"timeout_s": 17, "provider_option": {"opaque": True}}},
            {
                "max_tasks": 90,
                "max_concurrent": 16,
                "retry_attempts": 1,
                "field_limit": 2000,
                "pass_threshold": 1.0,
                "debugger": {"timeout_s": 17, "provider_option": {"opaque": True}},
            },
        ),
        (
            "analyze",
            "gepa",
            {"components": {"prompt": "target/prompt.md"}, "max_cases": 5, "field_limit": 800},
            {"components": {"prompt": ["target/prompt.md"]}, "max_cases": 5, "field_limit": 800},
        ),
        (
            "mutate",
            "aevolve",
            {
                "runner": "harbor",
                "environment_kwargs": {"provider": {"opaque": True}},
                "agent_kwargs": {"reasoning": {"effort": "high"}},
                "agent_env": {"TOKEN": {"from": "provider"}},
                "trajectory_only": True,
                "expose_gate_data": False,
                "editable_roots": ["target", "operators"],
                "evolve_prompts": True,
                "evolve_skills": False,
                "evolve_memory": False,
                "history_cycles": 3,
                "max_observations": 8,
                "feedback_chars": 250,
                "evidence_chars": 1000,
                "required_placeholders": ["{{ instruction }}"],
                "max_retries": 2,
            },
            {
                "runner": "harbor",
                "environment_kwargs": {"provider": {"opaque": True}},
                "agent_kwargs": {"reasoning": {"effort": "high"}},
                "agent_env": {"TOKEN": {"from": "provider"}},
                "trajectory_only": True,
                "expose_gate_data": False,
                "editable_roots": ["target", "operators"],
                "evolve_prompts": True,
                "evolve_skills": False,
                "evolve_memory": False,
                "history_cycles": 3,
                "max_observations": 8,
                "feedback_chars": 250,
                "evidence_chars": 1000,
                "required_placeholders": ["{{ instruction }}"],
                "max_retries": 2,
            },
        ),
        (
            "mutate",
            "gepa",
            {"components": {"skill": "target/skills/task"}},
            {
                "runner": "local",
                "expose_gate_data": False,
                "editable_roots": ["target"],
                "components": {"skill": ["target/skills/task"]},
                "component_strategy": "round_robin",
                "max_examples": 10,
                "required_placeholders": [],
                "max_retries": 0,
            },
        ),
        (
            "validate",
            "minibatch_improvement",
            {
                "criterion": "non_decreasing",
                "verifier_timeout_multiplier": 3,
                "environment_kwargs": {"opaque": {"x": 1}},
            },
            {
                "criterion": "non_decreasing",
                "verifier_timeout_multiplier": 3.0,
                "environment_kwargs": {"opaque": {"x": 1}},
            },
        ),
        ("novelty", "diff_similarity", {}, {"threshold": 0.98, "history_k": 8}),
        ("record", "jsonl", {}, {}),
    ],
)
def test_operator_config_is_strictly_normalized(
    stage: str,
    name: str,
    config: dict[str, object],
    expected: dict[str, object],
) -> None:
    assert validate_operator_config(resolve_operator(stage, name), config) == expected


@pytest.mark.parametrize("operator", discover_operators().values(), ids=lambda item: item.identity)
def test_every_library_operator_rejects_unknown_settings(operator: LibraryOperator) -> None:
    with pytest.raises(OperatorLibraryError, match="unexpected: unknown field"):
        validate_operator_config(operator, {"unexpected": True})


@pytest.mark.parametrize(
    ("stage", "name", "config", "message"),
    [
        ("select", "random", {"seed": True}, "seed: expected integer"),
        ("rollout", "harbor", {"budget_tasks": True}, "budget_tasks: expected integer"),
        ("rollout", "harbor", {"agent_setup_timeout_multiplier": 0}, "must be positive"),
        ("rollout", "harbor", {"environment_kwargs": []}, "environment_kwargs: expected object"),
        ("analyze", "trajectory_only", {"judge_timeout_s": True}, "judge_timeout_s: expected finite number"),
        ("analyze", "ahe", {"pass_threshold": True}, "pass_threshold: expected finite number"),
        ("mutate", "aevolve", {"editable_roots": "target"}, "editable_roots: expected array"),
        ("mutate", "hyperagents", {"expose_gate_data": 1}, "expose_gate_data: expected boolean"),
        ("mutate", "ahe", {"max_retries": True}, "max_retries: expected integer"),
        ("validate", "minibatch_improvement", {"criterion": "loose"}, "criterion: expected one of"),
        ("novelty", "diff_similarity", {"threshold": "0.9"}, "threshold: expected finite number"),
        ("novelty", "diff_similarity", {"threshold": 1.01}, "threshold: must be at most 1"),
    ],
)
def test_operator_config_rejects_malformed_values(
    stage: str,
    name: str,
    config: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(OperatorLibraryError, match=message):
        validate_operator_config(resolve_operator(stage, name), config)
