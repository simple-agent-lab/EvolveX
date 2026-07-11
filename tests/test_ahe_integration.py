import stat
from pathlib import Path

from conftest import ahe_debugger_command, ahe_editor_command, git, rows_by_genid, run_evolve


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _deterministic_evaluator() -> str:
    return """#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path


run_dir = Path(os.environ["EVOLVE_RUN_DIR"])
run_dir.mkdir(parents=True, exist_ok=True)
regressed = "# AHE_REGRESSION" in Path("target/agent.py").read_text()
outcomes = {"task-0": 0.0, "task-1": 0.0 if regressed else 1.0, "task-2": 1.0}
tasks = {
    task_id: {
        "trials": [
            {"trial": trial, "status": "complete", "reward": reward}
            for trial in range(2)
        ]
    }
    for task_id, reward in outcomes.items()
}
artifacts = run_dir / "artifacts"
artifacts.mkdir(exist_ok=True)
trials = []
for task_id in outcomes:
    trace = artifacts / f"{task_id}.md"
    trace.write_text(f"verified trace for {task_id}\\n")
    trials.append(
        {
            "task_name": task_id,
            "files": [{"path": trace.name, "sha256": hashlib.sha256(trace.read_bytes()).hexdigest()}],
        }
    )
(run_dir / "task_vector.json").write_text(json.dumps({"schema_version": 1, "tasks": tasks}) + "\\n")
(run_dir / "evaluation_artifacts.json").write_text(
    json.dumps({"jobs_dir": str(artifacts.resolve()), "trials": trials}) + "\\n"
)
(run_dir / "score").write_text("0.99\\n" if regressed else "1.0\\n")
(run_dir / "status").write_text("partial\\n")
raise SystemExit(2)
"""


def _configure_baseline_evaluator(workspace: Path) -> None:
    _write_executable(workspace / "evaluator" / "eval.sh", _deterministic_evaluator())
    git(workspace, "add", "evaluator/eval.sh")
    git(workspace, "commit", "-m", "configure deterministic AHE evaluator")
    git(workspace, "tag", "-f", "gen/0")


def test_ahe_two_iteration_loop_attributes_harm_and_rolls_back(tmp_path: Path) -> None:
    workspace = tmp_path / "ahe"
    evolve_home = tmp_path / "evolve-home"
    sealed_test_filename = "heldout-ahe-evaluation.txt"
    proxy_value = "http://proxy.example:8118"

    initialized = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "ahe-smoke",
        env={"EVOLVE_HOME": str(evolve_home)},
    )
    assert initialized.returncode == 0, initialized.stderr
    _configure_baseline_evaluator(workspace)

    baseline = run_evolve(
        "eval",
        str(workspace),
        "0",
        "--force",
        env={"EVOLVE_HOME": str(evolve_home)},
    )
    assert baseline.returncode == 0, baseline.stderr

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "2",
        env={
            "EVOLVE_HOME": str(evolve_home),
            "EVOLVE_AGENT_COMMAND": ahe_editor_command(),
            "EVOLVE_AHE_DEBUGGER_COMMAND": ahe_debugger_command(),
            "http_proxy": proxy_value,
            "https_proxy": proxy_value,
        },
    )

    assert result.returncode == 0, result.stderr
    rows = rows_by_genid(workspace)
    assert rows["0"]["score"] > rows["1"]["score"]
    assert rows["1"]["score"] == 0.99
    assert rows["1"]["valid_parent"] is True
    assert rows["1"]["ahe_decision"] == "keep"
    assert (workspace / str(rows["1"]["ahe_manifest_path"])).is_file()
    assert rows["2"]["parent"] == "1"
    assert rows["2"]["ahe_decision"] == "rollback_pivot"
    assert rows["2"]["ahe_attribution"]["HARMFUL"] == 1
    assert "target/agent.py" in rows["2"]["mutated"]
    assert (workspace / "runs/gen-2/rollout/attribution.json").exists()

    prompts = "\n".join(path.read_text() for path in workspace.glob("runs/**/received-prompt.md"))
    assert sealed_test_filename not in prompts
    assert proxy_value not in prompts
