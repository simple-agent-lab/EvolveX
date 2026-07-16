import json
from pathlib import Path

from conftest import run_evolve


def test_status_and_report_recompute_best_from_stamped_scores(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"
    evolve_home = tmp_path / "home"
    assert (
        run_evolve("init", str(workspace), "--recipe", "hill_climb-smoke", env={"EVOLVE_HOME": str(evolve_home)}).returncode
        == 0
    )
    run = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert run.returncode == 0, run.stderr
    with (workspace / "archive.jsonl").open("a") as archive:
        archive.write(
            json.dumps({"genid": "1", "score": 999.0, "status": "complete", "note": "malicious later row"}) + "\n"
        )

    status = run_evolve("status", str(workspace), env={"EVOLVE_HOME": str(evolve_home)})
    report = run_evolve("report", str(workspace), env={"EVOLVE_HOME": str(evolve_home)})

    assert status.returncode == 0, status.stderr
    assert "best_genid: 0" in status.stdout
    assert "best_score: 1.0" in status.stdout
    assert "rows: 2" in status.stdout
    assert report.returncode == 0, report.stderr
    assert "Research claim checklist" in report.stdout
    assert "task_set_hash: consistent" in report.stdout
    assert "unstamped_rows: 0" in report.stdout
