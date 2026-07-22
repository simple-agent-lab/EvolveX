from pathlib import Path

from conftest import run_evolve

from evolve.config import surface_lists


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
    assert "agent: mini-swe-agent" in config
    assert "editable_roots:" in config
    assert "- target" in config and "- operators" in config
    assert (workspace / "evaluator/agent.env").read_text() == (
        "MINISWE_COST_LIMIT=0\nMINISWE_REASONING_EFFORT=high\n"
    )
    prompt = (workspace / "operators/meta_agent.py").read_text()
    assert "substantive `target/**` change" in prompt
    assert "`operators/**` remains editable" in prompt
    assert "def _install_bundle(" in (workspace / "library/meta_agent/runners/harbor.py").read_text()
