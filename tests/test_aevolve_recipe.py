from pathlib import Path

from conftest import run_evolve


def test_aevolve_recipe_initializes_builtin_codex_workspace_contract(tmp_path: Path) -> None:
    workspace = tmp_path / "aevolve-workspace"
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "aevolve",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(tmp_path / "evolve-home")},
    )

    assert result.returncode == 0, result.stderr
    config = (workspace / "evolve.yaml").read_text()
    assert "seed: builtin-codex" in config
    assert "agent: target.agent:HarborAgent" in config
    assert "variant: trajectory_only" in config
    assert "trajectory_only: true" in config
    assert "expose_gate_data: false" in config
    assert "runner: harbor" in config
    assert "evolve_memory: false" in config
    assert "evolve_tools: false" in config
    assert "prompt_path: target/prompt.md" in config
    assert (workspace / "target" / "prompt.md").is_file()
    assert (workspace / "target" / "skills" / "task-execution" / "SKILL.md").is_file()
    operator = (workspace / "operators" / "meta_agent.py").read_text()
    assert "A-Evolve Workspace Improvement" in operator
    assert "class AEvolveMetaAgent" in operator
    analyzer = (workspace / "operators" / "trace_analyzer.py").read_text()
    assert "source=library/trace_analyzer/trajectory_only.py" in analyzer
    assert "class TrajectoryOnly" in analyzer
