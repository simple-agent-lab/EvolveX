import importlib.util
import json
import random
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from evolve.agent import AgentCommandError
from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "library" / "meta_agent" / "aevolve.py"
    spec = importlib.util.spec_from_file_location("aevolve_meta_agent_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> None:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


def _case(tmp_path: Path):
    workspace = tmp_path / "workspace"
    checkout = tmp_path / "checkout"
    run_dir = workspace / "runs" / "gen-2"
    target = checkout / "target"
    (target / "skills" / "existing").mkdir(parents=True)
    (target / "skills" / "existing" / "SKILL.md").write_text(
        "---\nname: existing\ndescription: existing skill\n---\n\n# Existing\n"
    )
    drafts = target / "skills" / "_drafts"
    drafts.mkdir()
    (drafts / "candidate.md").write_text("A draft about verifying generated artifacts.\n")
    (target / "prompt.md").write_text("Solve carefully.\n\n{{ instruction }}\n")
    (checkout / "evolve.yaml").write_text(
        "experiment:\n  id: aevolve\n"
        "surface:\n  include:\n    - target/**\n  exclude: []\n"
        "operators:\n  meta_agent: {variant: aevolve, runner: harbor}\n"
        "evaluator:\n  engine: harbor\n  dataset: test\n"
    )
    prior = workspace / "runs" / "gen-1" / "rollout"
    current = run_dir / "rollout"
    prior.mkdir(parents=True)
    current.mkdir(parents=True)
    (prior / "cases.json").write_text(
        json.dumps(
            [
                {
                    "task_name": "task-prior",
                    "outcome": "passed",
                    "reward": 1,
                    "verifier_output": "all checks passed",
                }
            ]
        )
    )
    long_feedback = "missing output artifact " + "x" * 400
    (current / "cases.json").write_text(
        json.dumps(
            [
                {
                    "task_name": "task-current",
                    "outcome": "failed",
                    "reward": 0,
                    "verifier_output": long_feedback,
                },
                {
                    "task_name": "infra-noise",
                    "outcome": "infra_error",
                    "reward": None,
                    "exception": {"type": "DockerError", "message": "daemon unavailable"},
                },
            ]
        )
    )
    evidence = run_dir / "feedback" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "history.json").write_text(json.dumps([{"genid": "1"}]))
    workspace.mkdir(exist_ok=True)
    (workspace / "archive.jsonl").write_text('{"genid":"1","score":1}\n')
    _git(checkout, "init", "-q")
    _git(checkout, "config", "user.name", "test")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-qm", "parent")
    _git(checkout, "tag", "gen/1")
    config = {
        "runner": "harbor",
        "prompt_path": "target/prompt.md",
        "skills_dir": "target/skills",
        "memory_dir": "target/memory",
        "tools_dir": "target/tools",
        "evolve_prompts": True,
        "evolve_skills": True,
        "evolve_memory": False,
        "evolve_tools": False,
        "history_cycles": 2,
        "max_observations": 30,
        "feedback_chars": 300,
    }
    ctx = OperatorContext(workspace, checkout, run_dir, "2", "1", None, 1, config, random.Random(0))
    return checkout, run_dir, ctx


def test_aevolve_reproduces_recent_summary_draft_and_workspace_mutation_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)

    def fake_run_agent(root: Path, prompt: str, actual_ctx: OperatorContext):
        assert root == checkout and actual_ctx == ctx
        assert '"task_id": "task-prior"' in prompt
        assert '"task_id": "task-current"' in prompt
        assert "infra-noise" not in prompt
        assert "A draft about verifying generated artifacts" in prompt
        assert "Current Skills (1)" in prompt and "- existing" in prompt
        assert "You CAN modify `target/prompt.md`" in prompt
        assert "target/memory" in prompt and "You CAN add or prune" not in prompt
        assert "x" * 300 not in prompt
        assert "Preserve the `{{ instruction }}` placeholder" in prompt
        (root / "target" / "prompt.md").write_text("Verify artifacts before finishing.\n\n{{ instruction }}\n")
        skill = root / "target" / "skills" / "artifact-verification"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: artifact-verification\ndescription: Verify generated artifacts\n---\n"
        )
        return SimpleNamespace(output="updated prompt and skill", usage={"usd": 0.12})

    monkeypatch.setattr(module, "run_agent", fake_run_agent)
    result = module.AEvolveMetaAgent().run(checkout, "unused fallback", ctx)

    assert set(result.changed) == {
        "target/prompt.md",
        "target/skills/_drafts/candidate.md",
        "target/skills/artifact-verification/",
    }
    assert not (checkout / "target" / "skills" / "_drafts" / "candidate.md").exists()
    report = json.loads((run_dir / "meta_agent" / "aevolve-report.json").read_text())
    assert report == {
        "drafts_reviewed": 1,
        "evo_number": "2",
        "mutated": True,
        "new_skills": 1,
        "skills_added": ["artifact-verification"],
        "skills_after": 2,
        "skills_before": 1,
        "skills_removed": [],
        "tasks_analyzed": 2,
        "usage": {"usd": 0.12},
    }
    assert "variant: aevolve" in result.notes
    assert "runner: harbor" in result.notes
    assert (run_dir / "meta_agent" / "patch.diff").is_file()


def test_aevolve_runner_failure_keeps_drafts_and_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)

    def fail(*_args, **_kwargs):
        raise AgentCommandError("failed", output="runner output", returncode=7, usage={"usd": 0.2})

    monkeypatch.setattr(module, "run_agent", fail)
    with pytest.raises(SystemExit, match="7"):
        module.AEvolveMetaAgent().run(checkout, "unused fallback", ctx)
    assert (checkout / "target" / "skills" / "_drafts" / "candidate.md").is_file()
    assert (run_dir / "meta_agent" / "output.txt").read_text() == "runner output"
    assert json.loads((run_dir / "meta_agent" / "usage.json").read_text()) == {"usd": 0.2}
