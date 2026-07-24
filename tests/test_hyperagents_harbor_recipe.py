from pathlib import Path

from conftest import run_evolve

from evolve.config import operator_blocks, surface_lists


def test_hyperagents_recipe_initializes_broad_harbor_bundle(tmp_path: Path) -> None:
    workspace = tmp_path / "hyperagents-workspace"
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hyperagents",
        "--seed",
        "builtin-dummy",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(tmp_path / "evolve-home")},
    )
    assert result.returncode == 0, result.stderr
    assert surface_lists(workspace) == (["target/**", "operators/**"], [])
    config = (workspace / "evolve.yaml").read_text()
    assert "variant: hyperagents" in config
    assert "runner: harbor" in config
    assert "expose_gate_data: true" in config
    assert "agent: evolve_harbor_agent:FileTaskMiniSweAgent" in config
    assert "editable_roots:" in config
    assert "- target" in config and "- operators" in config
    assert "agent_env" not in operator_blocks(workspace)["meta_agent"]
    assert (workspace / "evaluator/agent.env").read_text() == (
        "MINISWE_COST_LIMIT=0\nMINISWE_ENV_TIMEOUT=30\nMINISWE_REASONING_EFFORT=high\n"
        "MINISWE_STEP_LIMIT=100\n"
    )
    assert "task_scope: full" in config
    assert "evaluation_split: train" in config
    assert "tasks_per_round: 30" in config
    assert "\n  split:" not in config
    assert "k: 1" in config
    assert "n_concurrent: 10" in config
    prompt = (workspace / "operators/meta_agent.py").read_text()
    assert "Strongly prefer a substantive `target/**`" in prompt
    assert "operator-only proposal is allowed" in prompt
    assert "`operators/**` remains editable" in prompt
    assert "def _install_bundle(" in (workspace / "library/meta_agent/runners/harbor.py").read_text()
