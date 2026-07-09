import stat
from pathlib import Path

from conftest import init_workspace, rows_by_genid, run_evolve


def make_eval_script(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_evaluator_path_commit_is_invalid_and_eval_does_not_stamp_score(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    child = tmp_path / "child"
    forked = run_evolve("fork", str(workspace), "0", str(child), env={"EVOLVE_HOME": str(evolve_home)})
    assert forked.returncode == 0, forked.stderr
    make_eval_script(
        child / "evaluator" / "eval.sh",
        "#!/bin/sh\n"
        "set -eu\n"
        'mkdir -p "$EVOLVE_RUN_DIR"\n'
        "printf '999.0\\n' > \"$EVOLVE_RUN_DIR/score\"\n"
        "printf 'complete\\n' > \"$EVOLVE_RUN_DIR/status\"\n"
        "exit 0\n",
    )

    committed = run_evolve(
        "commit",
        str(workspace),
        str(child),
        "--parent",
        "0",
        "--genid",
        "1",
        env={"EVOLVE_HOME": str(evolve_home)},
    )
    assert committed.returncode == 0, committed.stderr
    row = rows_by_genid(workspace)["1"]
    assert row["status"] == "invalid_proposal"
    assert row["valid_parent"] is False
    assert row["score"] is None
    assert row["surface_violations"] == ["evaluator/eval.sh"]

    before = (workspace / "archive.jsonl").read_text().splitlines()
    evaluated = run_evolve(
        "eval",
        str(workspace),
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert evaluated.returncode == 0, evaluated.stderr
    assert (workspace / "archive.jsonl").read_text().splitlines() == before
    assert rows_by_genid(workspace)["1"]["score"] is None


def test_infra_failed_eval_is_scoreless_invalid_parent_and_retryable(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={"EVAL_STUB": None, "EVOLVE_HOME": str(evolve_home)},
    )
    assert first.returncode == 0, first.stderr

    failed = rows_by_genid(workspace)["1"]
    assert failed["status"] == "infra_failed"
    assert failed["score"] is None
    assert failed["valid_parent"] is False

    retried = run_evolve(
        "eval",
        str(workspace),
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert retried.returncode == 0, retried.stderr
    repaired = rows_by_genid(workspace)["1"]
    assert repaired["status"] == "complete"
    assert repaired["score"] == 1.0
    assert repaired["valid_parent"] is True
