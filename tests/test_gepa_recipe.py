from pathlib import Path

from conftest import run_evolve


def test_gepa_recipe_initializes_all_native_operators(tmp_path: Path) -> None:
    workspace = tmp_path / "gepa-workspace"
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "gepa",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(tmp_path / "evolve-home")},
    )

    assert result.returncode == 0, result.stderr
    config = (workspace / "evolve.yaml").read_text()
    assert "seed: builtin-codex" in config
    assert "variant: minibatch_improvement" in config
    assert "component_strategy: round_robin" in config
    assert "agent: target.agent:HarborAgent" in config
    assert "class ParetoSelect" in (workspace / "operators/select.py").read_text()
    assert "class GepaTraceAnalyzer" in (workspace / "operators/trace_analyzer.py").read_text()
    assert "class GepaMetaAgent" in (workspace / "operators/meta_agent.py").read_text()
    assert "class MinibatchImprovementValidate" in (workspace / "operators/validate.py").read_text()
    assert "class GepaRecord" in (workspace / "operators/record.py").read_text()
    assert (workspace / "library/gepa_support.py").is_file()
