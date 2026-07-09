from pathlib import Path

import pytest

from evolve.workspace import InitOptions, _eval_env, init_workspace


def test_eval_env_uses_configured_harbor_agent() -> None:
    env = _eval_env(
        "exp",
        "swe-bench-lite",
        n_concurrent=2,
        tasks_per_round=3,
        trials=1,
        partial_floor=0.8,
        agent="target.harbor_agent:MiniSweSourceAgent",
    )

    assert "EVOLVE_HARBOR_AGENT=target.harbor_agent:MiniSweSourceAgent\n" in env
    assert "CheckoutTargetAgent" not in env


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
            "meta_agent": {"variant": "noop"},
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
    assert "EVOLVE_HARBOR_AGENT=target.harbor_agent:MiniSweSourceAgent\n" in env
    assert "CheckoutTargetAgent" not in env
    assert not (workspace / "evaluator" / "checkout_agent.py").exists()
