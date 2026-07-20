from pathlib import Path

import pytest

from evolve import workspace as workspace_module
from evolve.workspace import InitOptions, _eval_env, init_workspace


def test_eval_env_uses_configured_harbor_agent() -> None:
    env = _eval_env(
        "exp",
        "swe-bench-lite",
        n_concurrent=2,
        tasks_per_round=3,
        trials=1,
        partial_floor=0.8,
        agent="evolve_harbor_adapter:MiniSweSourceAgent",
    )

    assert "EVOLVE_HARBOR_AGENT=evolve_harbor_adapter:MiniSweSourceAgent\n" in env
    assert "CheckoutTargetAgent" not in env


def test_eval_env_freezes_configured_model() -> None:
    env = _eval_env(
        "exp",
        "terminal-bench-2",
        n_concurrent=2,
        tasks_per_round=30,
        trials=1,
        partial_floor=0.8,
        agent="evolve_harbor_adapter:MiniSweSourceAgent",
        model="openai/gpt-5.4-2026-03-05",
    )

    assert "EVOLVE_HARBOR_MODEL=openai/gpt-5.4-2026-03-05\n" in env


def test_eval_env_freezes_agent_timeout_multiplier() -> None:
    env = _eval_env(
        "exp",
        "terminal-bench-2",
        n_concurrent=8,
        tasks_per_round=30,
        trials=1,
        partial_floor=0.8,
        agent="evolve_harbor_adapter:MiniSweSourceAgent",
        agent_timeout_multiplier=4,
    )

    assert "EVOLVE_HARBOR_AGENT_TIMEOUT_MULTIPLIER=4\n" in env


def test_agent_env_renders_frozen_miniswe_limits_deterministically() -> None:
    assert workspace_module._agent_env(
        {
            "MINISWE_STEP_LIMIT": "100",
            "MINISWE_ENV_TIMEOUT": 30,
            "MINISWE_COST_LIMIT": 3.0,
        }
    ) == ("MINISWE_COST_LIMIT=3.0\nMINISWE_ENV_TIMEOUT=30\nMINISWE_STEP_LIMIT=100\n")


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"BAD-NAME": "1"}, "invalid evaluator.agent_env name"),
        ({"GOOD": "first\nsecond"}, "single-line"),
        ({"GOOD": "first\0second"}, "NUL"),
        ({"GOOD": ["nested"]}, "scalar"),
        (["not", "a", "mapping"], "must be a mapping"),
    ],
)
def test_agent_env_rejects_unsafe_values(value: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        workspace_module._agent_env(value)


def test_init_real_harbor_recipe_requires_evaluator_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evolve import workspace as workspace_module

    config = {
        "experiment": {"id": "broken"},
        "target": {"seed": "builtin-dummy"},
        "surface": {"include": ["target/**"], "exclude": []},
        "operators": {
            "select": {"variant": "greedy"},
            "rollout": {"variant": "noop"},
            "meta_agent": {"variant": "hyperagents"},
            "gate": {"variant": "parent_eligible"},
            "record": {"variant": "jsonl"},
        },
        "evaluator": {"engine": "harbor", "dataset": "swe-bench-lite"},
    }
    monkeypatch.setattr(workspace_module, "default_config", lambda recipe, experiment_id: config)

    with pytest.raises(ValueError, match="evaluator.agent is required"):
        init_workspace(InitOptions(workspace=tmp_path / "w", recipe="broken"))


def test_init_writes_recipe_harbor_agent_to_eval_env(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    init_workspace(InitOptions(workspace=workspace, recipe="hill_climb-smoke"))

    env = (workspace / "evaluator" / "eval.env").read_text()
    assert "EVOLVE_HARBOR_AGENT=evolve_harbor_adapter:MiniSweSourceAgent\n" in env
    assert "CheckoutTargetAgent" not in env
    assert (workspace / "evaluator" / "agent.env").read_text() == ""
    assert not (workspace / "evaluator" / "checkout_agent.py").exists()
