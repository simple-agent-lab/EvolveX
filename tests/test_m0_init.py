import json
from pathlib import Path

from conftest import git, run_evolve, write_locked_miniswe_seed

from evolve.config import surface_lists


def _miniswe_seed(root: Path) -> Path:
    return write_locked_miniswe_seed(root / "miniswe")


def test_init_scaffolds_hill_climb_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"

    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hill_climb-smoke",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(tmp_path / "evolve-home")},
    )

    assert result.returncode == 0, result.stderr
    expected_paths = [
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        "evolve_harbor_adapter/__init__.py",
        "evolve_harbor_agent/__init__.py",
        "evolve.yaml",
        ".evolve-protocol-version",
        ".evolve/evolve/harbor_local.py",
        "AGENTS.md",
        "program.md",
        "operators/select.py",
        "operators/rollout.py",
        "operators/meta_agent.py",
        "operators/gate.py",
        "operators/record.py",
        "operators/engines/local.sh",
        "operators/preflight.sh",
        "operators/select.md",
        "operators/rollout.md",
        "operators/gate.md",
        "operators/record.md",
        "skills/evolve-workspace/SKILL.md",
        "target/agent.py",
        "target/README.md",
        "target/UPSTREAM.json",
        "evaluator/eval.sh",
        "evaluator/eval.env",
        "evaluator/environment.kwargs",
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
    assert not (workspace / "operators" / "mutate.py").exists()
    assert not (workspace / "operators" / "mutate.md").exists()
    assert not (workspace / "operators" / "mutation_brief.md").exists()
    assert not (workspace / "evolve_harbor_adapter" / "modelhub_codex.py").exists()
    assert not (workspace / "operators" / "meta_agent.md").exists()
    assert not (workspace / "operators" / "meta_agent_brief.md").exists()
    assert not (workspace / "evaluator" / "checkout_agent.py").exists()
    assert not (workspace / "target" / "harbor_agent.py").exists()
    assert (workspace / ".python-version").read_text() == "3.12\n"
    assert "harbor==0.18.0" in (workspace / "pyproject.toml").read_text()
    assert (
        'packages = [".evolve/evolve", "evolve_harbor_adapter", "evolve_harbor_agent", "library"]'
        in (workspace / "pyproject.toml").read_text()
    )

    config = (workspace / "evolve.yaml").read_text()
    assert "children_per_gen: 1" in config
    assert "mode: driver" in config
    assert "seed: builtin-dummy" in config
    assert "variant:" not in config
    assert "script:" not in config
    assert "meta_agent:\n    runner: local\n    timeout_s: 3600" in config
    assert "mutate:" not in config
    assert "- target/**" in config
    assert (workspace / ".evolve-protocol-version").read_text() == "1\n"
    upstream = json.loads((workspace / "target" / "UPSTREAM.json").read_text())
    assert upstream == {"kind": "builtin", "seed": "builtin-dummy"}

    gitignore = (workspace / ".gitignore").read_text()
    assert "runs/" in gitignore
    assert "archive.jsonl" in gitignore
    assert ".venv/" in gitignore

    splits = json.loads((workspace / "evaluator" / "splits.json").read_text())
    assert splits["version"] == 1
    assert splits["resolved"] is False
    assert splits["ratios"] == {"train": 0.5, "gate": 0.4, "sealed": 0.1}
    assert splits["tasks"] == {"train": [], "gate": [], "sealed": []}


def test_init_creates_generation_zero_git_snapshot_and_archive_event(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"

    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hill_climb-smoke",
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
    assert row["status"] == "pending"
    assert row["score"] is None
    assert row["valid_parent"] is False
    assert row["verdict"] == "pending"
    assert row["reason"] == "generation zero requires real evaluation"
    assert row["mutated"] == []
    assert row["surface_violations"] == []
    assert "task_set_hash" not in row
    assert "task_vector" not in row
    assert "evaluator_tree" not in row
    assert row["cost"]["usd"] == 0


def test_init_binds_real_hyperagents_method_surface_and_operators(tmp_path: Path) -> None:
    workspace = tmp_path / "hyperagents"
    seed = _miniswe_seed(tmp_path)

    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hyperagents",
        "--seed",
        str(seed),
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(tmp_path / "evolve-home")},
    )

    assert result.returncode == 0, result.stderr
    assert "score_child_prop" in (workspace / "operators/select.py").read_text()
    assert "EvaluationReplayRollout" in (workspace / "operators/rollout.py").read_text()
    assert (workspace / "library/rollout/harbor.py").is_file()
    assert "class TraceBrowser" in (workspace / "operators/trace_analyzer.py").read_text()
    assert "variant: hyperagents" in (workspace / "operators/meta_agent.py").read_text()
    assert "HyperAgents Self-Improvement" in (workspace / "operators/meta_agent.py").read_text()
    assert "HyperAgentsValidate" in (workspace / "operators/validate.py").read_text()
    assert "HyperAgentsRecord" in (workspace / "operators/record.py").read_text()
    assert surface_lists(workspace) == (["target/**", "operators/**"], [])


def test_init_tracks_vendored_files_ignored_by_seed_repository(tmp_path: Path) -> None:
    workspace = tmp_path / "ignored-lock"
    seed = _miniswe_seed(tmp_path)
    (seed / ".gitignore").write_text("uv.lock\n")

    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hyperagents",
        "--seed",
        str(seed),
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(tmp_path / "evolve-home")},
    )

    assert result.returncode == 0, result.stderr
    assert "target/uv.lock" in git(workspace, "ls-files", "target/uv.lock").splitlines()
