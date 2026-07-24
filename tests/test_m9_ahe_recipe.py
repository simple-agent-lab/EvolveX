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
    assert "source=library/rollout/evaluation_replay.py" in (workspace / "operators/rollout.py").read_text()
    assert (workspace / "library/rollout/harbor.py").is_file()
    assert "source=library/trace_analyzer/ahe.py" in (workspace / "operators/trace_analyzer.py").read_text()
    assert "source=library/meta_agent/ahe.py" in (workspace / "operators/meta_agent.py").read_text()
    assert "source=library/select/ahe_latest.py" in (workspace / "operators/select.py").read_text()
    assert "source=library/gate/ahe_artifact_valid.py" in (workspace / "operators/gate.py").read_text()
    for relative in (
        "library/meta_agent/runners/__init__.py",
        "library/meta_agent/runners/local.py",
        "library/meta_agent/runners/harbor.py",
        "library/meta_agent/support/evidence.py",
    ):
        assert (workspace / relative).is_file(), relative
    assert (workspace / "evolve_harbor_adapter/__init__.py").is_file()
    assert (workspace / "evolve_harbor_agent/__init__.py").is_file()
    assert not (workspace / "target/harbor_agent.py").exists()
    assert not (workspace / "library/meta_agent/support/ahe_manifest.py").exists()
    assert (workspace / "evaluator/agent.env").read_text() == (
        "MINISWE_COST_LIMIT=0\nMINISWE_ENV_TIMEOUT=30\nMINISWE_REASONING_EFFORT=high\n"
        "MINISWE_STEP_LIMIT=100\n"
        "OPENAI_BASE_URL=https://aidp.bytedance.net/api/modelhub/online/responses/openai/responses\n"
    )
    config = (workspace / "evolve.yaml").read_text()
    assert "variant: ahe" in config
    assert "runner: harbor" in config
    assert "agent: evolve_harbor_agent:FileTaskMiniSweAgent" in config
    assert "editable_roots:" in config
    operators = operator_blocks(workspace)
    assert operators["meta_agent"]["agent_env"] == {
        "OPENAI_BASE_URL": "https://aidp.bytedance.net/api/modelhub/online/responses/openai/responses"
    }
    assert {name: operator_timeout(operators, name) for name in ("rollout", "trace_analyzer", "meta_agent")} == {
        "rollout": 600,
        "trace_analyzer": 3600,
        "meta_agent": 3600,
    }
    assert operators["trace_analyzer"] == {
        "variant": "ahe",
        "max_tasks": 10,
        "max_concurrent": 10,
        "timeout_per_task": 600,
        "retry_attempts": 3,
        "debugger_agent_kwargs": {"reasoning_effort": "high", "max_tokens": 64000},
        "field_limit": 2000,
        "timeout_s": 3600,
    }
    config = (workspace / "evolve.yaml").read_text()
    assert "budget_usd" not in config
    assert "max_cases" not in config
    assert "  evaluation_split: train" in config
    assert "  k: 1" in config
    assert "  n_concurrent: 10" in config
