from pathlib import Path

from conftest import init_workspace, run_evolve


def test_no_framework_feedback_bundle_is_created(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    assert not (workspace / "runs/gen-1/feedback").exists()
    assert (workspace / "runs/gen-1/rollout/summary.json").exists()
