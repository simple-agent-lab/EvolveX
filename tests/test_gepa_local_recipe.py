"""End-to-end test of the gepa_local recipe: real local Harbor trials,
no Docker, no model, no EVAL_STUB.

This locks the three traps the recipe exists to remove: Harbor task-directory
discovery requirements, the validate stage falling back to Docker, and the
candidate contract (agents must read candidate files via
EVOLVE_CANDIDATE_SOURCE so admission minibatches evaluate the child, not the
parent).
"""

import json
from pathlib import Path

from conftest import run_evolve

TASKS_LOCAL = Path(__file__).parent / "fixtures" / "tasks-local"


def _row_for(workspace: Path, genid: str) -> dict:
    rows = [json.loads(line) for line in (workspace / "archive.jsonl").read_text().splitlines()]
    scored = [r for r in rows if r.get("genid") == genid and r.get("score") is not None]
    assert scored, f"no scored archive row for gen {genid}"
    return scored[-1]


def test_eval_stub_targets_the_resolved_split(tmp_path: Path) -> None:
    """EVAL_STUB with a resolved dataset scores exactly the evaluated split's
    members instead of a synthetic full task suite (which used to fail the
    evaluation with unexpected extra trial evidence)."""
    workspace = tmp_path / "ws"
    result = run_evolve(
        "init", str(workspace), "--recipe", "gepa_local", "--dataset", str(TASKS_LOCAL)
    )
    assert result.returncode == 0, result.stderr

    result = run_evolve("run", str(workspace), "--max-generations", "0", env={"EVAL_STUB": "1"})
    assert result.returncode == 0, result.stderr

    row = _row_for(workspace, "0")
    assert row["status"] == "complete"
    assert row["score"] == 1.0
    gate_members = json.loads((workspace / "evaluator" / "splits.json").read_text())["tasks"]["gate"]
    assert sorted(row["task_vector"]["tasks"]) == sorted(gate_members)


def test_gepa_local_full_generation_improves_champion(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"

    result = run_evolve(
        "init", str(workspace), "--recipe", "gepa_local", "--dataset", str(TASKS_LOCAL)
    )
    assert result.returncode == 0, result.stderr

    # Real local baseline: the builtin-local-smoke seed only knows "1 + 1",
    # so every gate task fails and the certified baseline is 0.0.
    result = run_evolve("run", str(workspace), "--max-generations", "0")
    assert result.returncode == 0, result.stderr
    assert _row_for(workspace, "0")["score"] == 0.0

    # Agent-led generation: select, fork, rollout on the train split.
    assert run_evolve("operator", "run", str(workspace), "select", "--genid", "1").returncode == 0
    child = workspace / "runs" / "worktrees" / "gen-1"
    assert run_evolve("fork", str(workspace), "0", str(child)).returncode == 0
    result = run_evolve(
        "operator", "run", str(workspace), "rollout",
        "--genid", "1", "--parent", "0", "--checkout", str(child),
    )
    assert result.returncode == 0, result.stderr
    rollout = json.loads((workspace / "runs" / "gen-1" / "rollout" / "summary.json").read_text())
    assert rollout["tasks_observed"] > 0
    assert rollout["passed"] == 0

    # Evidence-linked mutation inside the mutable surface: teach the
    # knowledge document the answers the rollout showed it was missing.
    knowledge_path = child / "target" / "knowledge.md"
    facts = {
        "7 + 5": "12", "6 * 7": "42", "9 - 4": "5", "8 + 3": "11",
        "5 * 5": "25", "10 / 2": "5", "4 + 9": "13", "12 - 5": "7",
        "3 * 3": "9", "2 + 2": "4",
    }
    knowledge_path.write_text(
        knowledge_path.read_text()
        + "".join(f"- {question} = {answer}\n" for question, answer in facts.items())
    )

    assert run_evolve("surface-check", str(child), "--parent", "0").returncode == 0
    result = run_evolve(
        "operator", "run", str(workspace), "validate",
        "--genid", "1", "--parent", "0", "--checkout", str(child),
    )
    assert result.returncode == 0, result.stderr
    comparison = json.loads(
        (workspace / "runs" / "gen-1" / "validate" / "comparison.json").read_text()
    )
    # The child must be evaluated from its own snapshot (candidate contract),
    # in the local environment (no Docker fallback), and it must win.
    assert comparison["child_infra_cases"] == []
    assert comparison["accepted"] is True
    assert comparison["child_total"] > comparison["parent_total"]

    assert (
        run_evolve(
            "commit", str(workspace), str(child), "--parent", "0", "--genid", "1"
        ).returncode
        == 0
    )
    assert run_evolve("eval", str(workspace), "1").returncode == 0
    assert run_evolve("finalize", str(workspace), "1", "--parent", "0").returncode == 0
    assert run_evolve("verify", str(workspace)).returncode == 0

    assert _row_for(workspace, "1")["score"] == 1.0
    champion = json.loads((workspace / "best_ever.json").read_text())
    assert champion["genid"] == "1"
