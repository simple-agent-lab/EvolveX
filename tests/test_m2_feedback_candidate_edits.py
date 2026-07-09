import json
from pathlib import Path

from conftest import init_workspace, rows_by_genid, run_evolve


def test_agent_command_smoke_ten_generations_has_monotone_best_and_feedback_bundle(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "10",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    rows = list(rows_by_genid(workspace).values())
    assert [row["genid"] for row in rows] == [str(gen) for gen in range(11)]
    best = []
    current = float("-inf")
    for row in rows:
        if row.get("score") is not None:
            current = max(current, float(row["score"]))
        best.append(current)
    assert best == sorted(best)
    assert best[-1] >= best[0]

    expected_feedback = {
        "index.md",
        "lineage.json",
        "attempts.md",
        "failures",
        "last_accepted.diff",
        "falsification.md",
        "rules.md",
    }
    for gen in range(1, 11):
        feedback = workspace / "runs" / f"gen-{gen}" / "feedback"
        assert {path.name for path in feedback.iterdir()} >= expected_feedback
        assert "failures/" in (feedback / "index.md").read_text()
        assert (
            "written-by: operators/meta_agent.py"
            in (workspace / "runs" / f"gen-{gen}" / "meta_agent" / "rationale.md").read_text()
        )
        assert json.loads((workspace / "runs" / f"gen-{gen}" / "gate.json").read_text())["verdict"] == "keep"

    last_accepted = (workspace / "runs" / "gen-10" / "feedback" / "last_accepted.diff").read_text()
    assert "# smoke-meta-agent gen 9" in last_accepted
