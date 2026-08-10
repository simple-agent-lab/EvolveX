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
    path = ROOT / "library" / "mutate" / "aevolve.py"
    spec = importlib.util.spec_from_file_location("aevolve_mutate_under_test", path)
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
        "operators:\n  mutate: {variant: aevolve, runner: harbor}\n"
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
    (evidence / "selected.md").write_text(
        "# Selected execution evidence\n\n"
        "Across failed tasks, the agent stopped after producing an approximation and did not verify exact output paths.\n"
    )
    (run_dir / "feedback" / "index.md").write_text(
        "# Feedback Bundle\n\n"
        "- [selected trace evidence](evidence/selected.md)\n"
        "- [rollout and edit history](evidence/history.json)\n"
    )
    workspace.mkdir(exist_ok=True)
    (workspace / "archive.jsonl").write_text('{"genid":"1","score":1}\n')
    handoff = workspace / "artifacts" / "generations" / "1" / "handoff.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("AEVOLVE HANDOFF BODY MUST STAY ON DISK\n")
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
        "evolve_prompts": True,
        "evolve_skills": True,
        "evolve_memory": False,
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
        assert '"task_id": "infra-noise"' in prompt
        assert "DockerError: daemon unavailable" in prompt
        assert "A draft about verifying generated artifacts" in prompt
        assert "Current Skills (1)" in prompt and "- existing" in prompt
        assert "Reusable skill directories: `target/skills/*/`" in prompt
        assert "references/`, `scripts/`, `assets/`" in prompt
        assert "You CAN modify any file under `target/`" in prompt
        assert "Runtime prompt/config: `target/prompt.md`" in prompt
        assert "Skills evolution: enabled" in prompt
        assert "Memory evolution: disabled" in prompt
        assert "target/memory" in prompt
        assert "x" * 300 not in prompt
        assert "Selected execution evidence" in prompt
        assert "did not verify exact output paths" in prompt
        assert "runs/gen-2/feedback/evidence/selected.md" in prompt
        assert "runs/gen-2/analyze/evidence/" in prompt
        assert "Preserve the `{{ instruction }}` placeholder" in prompt
        assert "selected parent's handoff" in prompt
        assert "/app/task/workspace/artifacts/generations/1/handoff.md" in prompt
        assert "/app/task/workspace/artifacts/generations/2" in prompt
        assert "AEVOLVE HANDOFF BODY MUST STAY ON DISK" not in prompt
        (root / "target" / "prompt.md").write_text("Verify artifacts before finishing.\n\n{{ instruction }}\n")
        skill = root / "target" / "skills" / "artifact-verification"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: artifact-verification\ndescription: Verify generated artifacts\n---\n"
        )
        return SimpleNamespace(output="updated prompt and skill", usage={"usd": 0.12})

    monkeypatch.setattr(module, "run_agent", fake_run_agent)
    result = module.AEvolveMutate().mutate(checkout, "unused fallback", ctx)

    assert set(result.changed) == {
        "target/prompt.md",
        "target/skills/_drafts/candidate.md",
        "target/skills/artifact-verification/",
    }
    assert not (checkout / "target" / "skills" / "_drafts" / "candidate.md").exists()
    report = json.loads((run_dir / "mutate" / "aevolve-report.json").read_text())
    assert report == {
        "drafts_reviewed": 1,
        "evo_number": "2",
        "mutated": True,
        "new_skills": 1,
        "skills_added": ["artifact-verification"],
        "skills_after": 2,
        "skills_before": 1,
        "skills_removed": [],
        "tasks_analyzed": 3,
        "usage": {"usd": 0.12},
    }
    assert "operator: aevolve" in result.notes
    assert "runner: harbor" in result.notes
    assert (run_dir / "mutate" / "patch.diff").is_file()


def test_aevolve_runner_failure_keeps_drafts_and_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)

    def fail(*_args, **_kwargs):
        raise AgentCommandError("failed", output="runner output", returncode=7, usage={"usd": 0.2})

    monkeypatch.setattr(module, "run_agent", fail)
    with pytest.raises(SystemExit, match="7"):
        module.AEvolveMutate().mutate(checkout, "unused fallback", ctx)
    assert (checkout / "target" / "skills" / "_drafts" / "candidate.md").is_file()
    assert (run_dir / "mutate" / "output.txt").read_text() == "runner output"
    assert json.loads((run_dir / "mutate" / "usage.json").read_text()) == {"usd": 0.2}


def test_aevolve_prompt_path_is_a_component_location_not_a_permission_boundary(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)
    ctx.config.update({"evolve_skills": False, "editable_roots": ["target"]})

    prompt, _state = module.build_prompt(checkout, ctx)

    assert "You CAN modify any file under `target/`" in prompt
    assert "Runtime prompt/config: `target/prompt.md`" in prompt
    assert "Skills evolution: disabled" in prompt
    assert "Review draft skills" not in prompt
    assert "Candidate-owned tools" not in prompt
    assert "Tools evolution" not in prompt
    assert "- Tools:" not in prompt
    assert "Do not add standalone files to a disabled context layer" in prompt


def test_aevolve_keeps_drafts_when_skill_evolution_is_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)
    ctx.config["evolve_skills"] = False
    monkeypatch.setattr(
        module,
        "run_agent",
        lambda *_args, **_kwargs: SimpleNamespace(output="no skill changes", usage={"usd": 0}),
    )

    module.AEvolveMutate().mutate(checkout, "fallback", ctx)

    assert (checkout / "target/skills/_drafts/candidate.md").is_file()
    report = json.loads((run_dir / "mutate/aevolve-report.json").read_text())
    assert report["drafts_reviewed"] == 0


def test_aevolve_rejects_directory_as_prompt_path(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)
    ctx.config["prompt_path"] = "target"

    with pytest.raises(ValueError, match="prompt_path must reference an existing file"):
        module.build_prompt(checkout, ctx)


def test_aevolve_bounds_inline_evidence_and_keeps_complete_path(tmp_path: Path) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)
    selected = run_dir / "feedback" / "evidence" / "selected.md"
    selected.write_text("distinctive evidence prefix\n" + "z" * 2_000 + "\ndistinctive evidence suffix\n")
    ctx.config["evidence_chars"] = 400

    prompt, _state = module.build_prompt(checkout, ctx)

    assert "distinctive evidence prefix" in prompt
    assert "distinctive evidence suffix" not in prompt
    assert "inline evidence truncated" in prompt
    assert "runs/gen-2/feedback/" in prompt


def test_aevolve_uses_operator_observation_when_feedback_bundle_is_missing(tmp_path: Path) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)
    (run_dir / "feedback" / "index.md").unlink()

    prompt, _state = module.build_prompt(checkout, ctx, "fallback analyzer observation")

    assert "fallback analyzer observation" in prompt


def test_aevolve_trajectory_only_prompt_has_one_behavior_evidence_section_and_no_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)
    trace_evidence = run_dir / "analyze" / "evidence"
    trace_evidence.mkdir(parents=True)
    (trace_evidence / "manifest.json").write_text(
        json.dumps(
            {
                "analyze_operator": "trajectory_only",
                "evidence_policy": "trajectory_only",
                "ground_truth_exposed": False,
                "cases": 1,
            }
        )
    )
    selected = (
        "### Agent Behavior Analysis (this batch)\n\n"
        "You can ONLY see the agent's actions. You do NOT have access to actual test results.\n\n"
        "```json\n"
        '[{"task_id":"task-current","signals":{"n_tool_calls":2},'
        '"compressed_trajectory":"Commands: 2, Errors: 1, Submitted: false",'
        '"judge_verdict":{"score":2,"category":"debug","outcome":"likely failed",'
        '"failure_reason":"stopped after an error"}}]\n'
        "```\n"
    )
    (run_dir / "feedback" / "evidence" / "selected.md").write_text(selected)
    ctx.config["trajectory_only"] = True
    monkeypatch.setattr(
        module,
        "_case_summaries",
        lambda _ctx: (_ for _ in ()).throw(AssertionError("trajectory-only must not read labeled cases")),
    )

    prompt, state = module.build_prompt(checkout, ctx)

    assert state["trajectory_only"] is True
    assert state["tasks_analyzed"] == 1
    assert prompt.count("### Agent Behavior Analysis (this batch)") == 1
    assert "### Task Summaries" not in prompt
    assert "Trace-Analyzer Feedback" not in prompt
    assert "feedback/index.md" not in prompt
    assert '"success":' not in prompt
    assert '"reward":' not in prompt
    assert '"score":2' in prompt
    assert "all checks passed" not in prompt
    assert "missing output artifact" not in prompt
    assert "Raw trace evidence:" not in prompt
    assert "runs/gen-2/" not in prompt
    assert "do not search for evaluator labels or test feedback" in prompt
