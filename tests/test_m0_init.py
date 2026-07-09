import json
from pathlib import Path

from conftest import git, run_evolve


def test_init_scaffolds_hill_climb_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"

    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hill_climb",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(tmp_path / "evolve-home")},
    )

    assert result.returncode == 0, result.stderr
    expected_paths = [
        "evolve.yaml",
        ".evolve-protocol-version",
        "AGENTS.md",
        "program.md",
        "operators/select.py",
        "operators/rollout.py",
        "operators/mutate.py",
        "operators/gate.py",
        "operators/record.py",
        "operators/engines/local.sh",
        "operators/preflight.sh",
        "operators/select.md",
        "operators/rollout.md",
        "operators/mutate.md",
        "operators/gate.md",
        "operators/record.md",
        "operators/mutation_brief.md",
        "skills/evolve-workspace/SKILL.md",
        "target/agent.py",
        "target/README.md",
        "target/UPSTREAM.json",
        "evaluator/eval.sh",
        "evaluator/eval.env",
        "evaluator/splits.json",
        "evaluator/dataset.pin",
        "evaluator/parse_score.py",
        "evaluator/engines/local.sh",
        "runs",
        ".gitignore",
        "archive.jsonl",
    ]
    for relative_path in expected_paths:
        assert (workspace / relative_path).exists(), relative_path

    config = (workspace / "evolve.yaml").read_text()
    assert "children_per_gen: 1" in config
    assert "mode: driver" in config
    assert "seed: builtin-dummy" in config
    assert "variant:" not in config
    assert "script:" not in config
    assert "mutate: {timeout_s: 3600}" in config
    assert "- target/**" in config
    assert (workspace / ".evolve-protocol-version").read_text() == "1\n"

    upstream = json.loads((workspace / "target" / "UPSTREAM.json").read_text())
    assert upstream == {"kind": "builtin", "seed": "builtin-dummy"}

    gitignore = (workspace / ".gitignore").read_text()
    assert "runs/" in gitignore
    assert "archive.jsonl" in gitignore

    splits = json.loads((workspace / "evaluator" / "splits.json").read_text())
    assert set(splits) == {"train", "gate", "sealed", "seed"}


def test_init_creates_generation_zero_git_snapshot_and_archive_event(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"

    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hill_climb",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(tmp_path / "evolve-home")},
    )

    assert result.returncode == 0, result.stderr
    assert git(workspace, "tag", "--list", "gen/0") == "gen/0"
    assert git(workspace, "rev-parse", "gen/0^{commit}") == git(workspace, "rev-parse", "HEAD")
    assert "gen 0" in git(workspace, "log", "-1", "--pretty=%s").lower()

    status_lines = git(workspace, "status", "--short").splitlines()
    assert status_lines == [], status_lines

    archive_lines = (workspace / "archive.jsonl").read_text().splitlines()
    assert len(archive_lines) == 1
    row = json.loads(archive_lines[0])
    assert row["genid"] == "0"
    assert row["parent"] is None
    assert row["tag"] == "gen/0"
    assert row["status"] == "complete"
    assert row["score"] == 1.0
    assert row["valid_parent"] is True
    assert row["mutated"] == []
    assert row["surface_violations"] == []
    assert row["task_set_hash"]
    assert row["evaluator_tree"]
    assert row["cost"]["usd"] == 0
