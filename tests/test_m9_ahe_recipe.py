from pathlib import Path

from conftest import run_evolve, write_locked_miniswe_seed

from evolve.config import operator_blocks, surface_lists
from evolve.operators import operator_timeout


def _dataset(root: Path, count: int = 10) -> Path:
    root.mkdir()
    for index in range(count):
        task = root / f"task-{index}"
        task.mkdir()
        (task / "task.toml").write_text(f'version = "1.0"\nname = "task-{index}"\n')
    return root


def test_ahe_recipe_initializes_harbor_miniswe_composition(tmp_path: Path) -> None:
    workspace = tmp_path / "ahe-workspace"
    seed = write_locked_miniswe_seed(tmp_path / "miniswe-seed")
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "ahe",
        "--dataset",
        str(_dataset(tmp_path / "tasks")),
        "--seed",
        str(seed),
        env={"EVOLVE_HOME": str(tmp_path / "evolve-home")},
    )
    assert result.returncode == 0, result.stderr
    assert (workspace / "target/pyproject.toml").is_file()
    assert (workspace / "target/uv.lock").is_file()
    assert surface_lists(workspace) == (["target/**"], [])
    assert "source=library/rollout/harbor.py" in (workspace / "operators/rollout.py").read_text()
    assert "source=library/trace_analyzer/ahe.py" in (workspace / "operators/trace_analyzer.py").read_text()
    assert "source=library/meta_agent/ahe.py" in (workspace / "operators/meta_agent.py").read_text()
    assert "source=library/gate/hillclimb.py" in (workspace / "operators/gate.py").read_text()
    for relative in (
        "library/meta_agent/runners/__init__.py",
        "library/meta_agent/runners/local.py",
        "library/meta_agent/runners/harbor.py",
        "library/meta_agent/runners/editable_bundle.py",
        "library/meta_agent/support/evidence.py",
    ):
        assert (workspace / relative).is_file(), relative
    assert (workspace / "target/harbor_agent.py").is_file()
    assert (workspace / "evaluator/agent.env").read_text() == (
        "MINISWE_COST_LIMIT=3.0\nMINISWE_ENV_TIMEOUT=30\nMINISWE_STEP_LIMIT=100\n"
    )
    config = (workspace / "evolve.yaml").read_text()
    assert "variant: ahe" in config
    assert "runner: harbor" in config
    assert "agent: mini-swe-agent" in config
    assert "editable_roots:" in config
    operators = operator_blocks(workspace)
    assert {name: operator_timeout(operators, name) for name in ("rollout", "trace_analyzer", "meta_agent")} == {
        "rollout": 3600,
        "trace_analyzer": 600,
        "meta_agent": 3600,
    }
