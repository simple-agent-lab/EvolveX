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
    assert "task_execution_skill: target/skills/task-execution\n" in config
    assert "task_execution_skill: target/skills/task-execution/SKILL.md" not in config
    assert "expose_gate_data: false" in config
    assert "agent: target.agent:HarborAgent" in config
    assert "class ParetoSelect" in (workspace / "operators/select.py").read_text()
    assert "class GepaAnalyze" in (workspace / "operators/analyze.py").read_text()
    assert "class GepaMutate" in (workspace / "operators/mutate.py").read_text()
    assert "class MinibatchImprovementValidate" in (workspace / "operators/validate.py").read_text()
    assert "class GepaRecord" in (workspace / "operators/record.py").read_text()
    assert (workspace / "library/_shared/gepa.py").is_file()
    mutate = (workspace / "library/mutate/gepa.py").read_text()
    assert "## Reflective dataset" not in mutate
    assert "component_evidence" in mutate
