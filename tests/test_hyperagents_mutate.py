import importlib.util
import json
import random
import subprocess
from pathlib import Path
from types import SimpleNamespace

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _load_hyperagents_mutate():
    spec = importlib.util.spec_from_file_location(
        "hyperagents_mutate_under_test",
        ROOT / "library" / "mutate" / "hyperagents.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _checkout(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    checkout = tmp_path / "checkout"
    run_dir = workspace / "runs" / "gen-1"
    (workspace / "runs" / "gen-0" / "eval").mkdir(parents=True)
    (workspace / "archive.jsonl").write_text(json.dumps({"genid": "0", "score": 0.1}) + "\n")
    (workspace / "runs" / "gen-0" / "eval" / "summary.json").write_text('{"score": 0.1}\n')
    handoff = workspace / "artifacts" / "generations" / "0" / "handoff.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("PARENT HANDOFF BODY MUST STAY ON DISK\n")
    (workspace / "evolve.yaml").write_text(
        "experiment:\n  id: test\n  max_generations: 4\n"
        "target:\n  seed: builtin-dummy\n"
        "surface:\n  include:\n    - target/**\n    - operators/**\n  exclude: []\n"
        "operators:\n  mutate: {operator: hyperagents, timeout_s: 30, config: {}}\n"
        "evaluator:\n  engine: harbor\n  dataset: pass@k\n"
        "  agent: evolve.integrations.harbor.miniswe_candidate:MiniSweSourceAgent\n"
    )
    (checkout / "target").mkdir(parents=True)
    (checkout / "operators").mkdir()
    (checkout / "target" / "agent.py").write_text("print('parent')\n")
    (checkout / "target" / "prompt.md").write_text("Solve carefully.\n")
    (checkout / "operators" / "mutate.py").write_text("# parent mutation operator\n")
    (checkout / "evolve.yaml").write_text((workspace / "evolve.yaml").read_text())
    _git(checkout, "init", "-q")
    _git(checkout, "config", "user.name", "test")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-qm", "parent")
    _git(checkout, "tag", "gen/0")
    return checkout, run_dir


def _ctx(workspace: Path, checkout: Path, run_dir: Path) -> OperatorContext:
    return OperatorContext(
        workspace=workspace,
        checkout=checkout,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={"runner": "local", "timeout_s": 30},
        rng=random.Random(0),
    )


def test_hyperagents_prompt_points_to_evolvable_codebase_and_prior_artifacts(tmp_path: Path) -> None:
    module = _load_hyperagents_mutate()
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(run_dir.parents[1], checkout, run_dir)
    ctx.config["runner"] = "harbor"
    evidence = run_dir / "feedback" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "selected.md").write_text("SELECTED TRACE EVIDENCE\n")
    (evidence / "history.json").write_text('"HISTORY MUST NOT BE INLINED"\n')
    (run_dir / "feedback" / "attempts.md").write_text("COMPACT ATTEMPTS FALLBACK\n")
    (run_dir / "feedback" / "last_accepted.diff").write_text("LATEST ACCEPTED DIFF\n")
    (run_dir / "feedback" / "index.md").write_text(
        "# Feedback Bundle\n\n"
        "- [selected trace evidence](evidence/selected.md)\n"
        "- [complete history](evidence/history.json)\n"
    )

    prompt = module.build_prompt(checkout, "fallback observation", ctx)

    assert module.PROMPT.startswith("# HyperAgents")
    assert "Repository: /app/task/workspace" in prompt
    assert "Archive: /app/task/workspace/archive.jsonl" in prompt
    assert "Prior generation artifacts: /app/task/workspace/runs" in prompt
    assert "Feedback bundle: /app/task/workspace/runs/gen-1/feedback" in prompt
    assert "Complete history: /app/task/workspace/runs/gen-1/feedback/evidence/history.json" in prompt
    assert "Raw trace evidence: /app/task/workspace/runs/gen-1/analyze/evidence" in prompt
    assert "selected parent's handoff" in prompt
    assert "/app/task/workspace/artifacts/generations/0/handoff.md" in prompt
    assert "/app/task/workspace/artifacts/generations/1" in prompt
    assert "PARENT HANDOFF BODY MUST STAY ON DISK" not in prompt
    assert "Evidence reading order" in prompt
    assert "1. Read `/app/task/workspace/runs/gen-1/feedback/index.md`" in prompt
    assert "/app/task/workspace/runs/gen-1/feedback/evidence/selected.md" in prompt
    assert "/app/task/workspace/runs/gen-1/feedback/last_accepted.diff" in prompt
    assert "/app/task/workspace/runs/gen-1/analyze/evidence" in prompt
    assert "/app/task/workspace/runs/gen-1/rollout" in prompt
    assert "SELECTED TRACE EVIDENCE" not in prompt
    assert "HISTORY MUST NOT BE INLINED" not in prompt
    assert "LATEST ACCEPTED DIFF" not in prompt
    assert "COMPACT ATTEMPTS FALLBACK" not in prompt
    assert "fallback observation" not in prompt
    assert "Iterations remaining after this proposal: 3" in prompt
    assert "Modify any part of the allowed codebase" in prompt
    assert "Strongly prefer a substantive `target/**`" in prompt
    assert "operator-only proposal is allowed" in prompt
    assert "must include at least one substantive `target/**` change" not in prompt
    assert "`operators/**` remains editable" in prompt
    assert "cosmetic target edits" in prompt
    assert "You are editing the MiniSWE source checkout under target/." not in prompt
    assert "You CAN modify any file under `target/`" in prompt
    assert "You CAN modify any file under `operators/`" in prompt
    assert "Runtime prompt/config: `target/prompt.md`" in prompt
    assert "Reusable skills: not configured or detected" in prompt
    assert "This method does not impose a narrower per-proposal path scope" in prompt


def test_hyperagents_prompt_does_not_read_large_evidence_bodies(tmp_path: Path) -> None:
    module = _load_hyperagents_mutate()
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(run_dir.parents[1], checkout, run_dir)
    evidence = run_dir / "feedback" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "selected.md").write_text("LARGE SELECTED BODY " * 10_000)
    (run_dir / "feedback" / "last_accepted.diff").write_text("LARGE DIFF BODY " * 10_000)

    prompt = module.build_prompt(checkout, "OBSERVATION BODY", ctx)

    assert "LARGE SELECTED BODY" not in prompt
    assert "LARGE DIFF BODY" not in prompt
    assert "OBSERVATION BODY" not in prompt
    assert len(prompt) < 10_000


def test_hyperagents_local_prompt_uses_existing_workspace_paths(tmp_path: Path) -> None:
    module = _load_hyperagents_mutate()
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(run_dir.parents[1], checkout, run_dir)

    prompt = module.build_prompt(checkout, "fallback", ctx)

    assert f"Repository: {checkout}" in prompt
    assert f"1. Read `{run_dir / 'feedback/index.md'}`" in prompt
    assert f"`{run_dir / 'feedback/evidence/selected.md'}`" in prompt
    assert f"`{run_dir / 'feedback/last_accepted.diff'}`" in prompt
    assert f"`{run_dir / 'rollout'}`" in prompt


def test_hyperagents_mutate_records_complete_patch_for_target_and_workflow_edits(tmp_path: Path, monkeypatch) -> None:
    module = _load_hyperagents_mutate()
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(run_dir.parents[1], checkout, run_dir)

    def fake_run_agent(workspace: Path, prompt: str, ctx: OperatorContext):
        assert workspace == checkout
        assert ctx.config["runner"] == "local"
        assert "Modify any part of the allowed codebase" in prompt
        assert "Evidence reading order" in prompt
        assert "observation" not in prompt
        (workspace / "target" / "agent.py").write_text("print('child')\n")
        (workspace / "operators" / "mutate.py").write_text("# improved mutation operator\n")
        return SimpleNamespace(output="edited target and workflow", usage={"usd": 0.02})

    monkeypatch.setattr(module, "run_agent", fake_run_agent)

    result = module.HyperAgentsMutate().mutate(checkout, "observation", ctx)

    assert set(result.changed) == {"target/agent.py", "operators/mutate.py"}
    diff = (run_dir / "mutate" / "model_patch.diff").read_text()
    assert "diff --git a/target/agent.py b/target/agent.py" in diff
    assert "diff --git a/operators/mutate.py b/operators/mutate.py" in diff
    assert (run_dir / "mutate" / "patch.diff").read_text() == diff
    assert json.loads((run_dir / "mutate" / "usage.json").read_text()) == {"usd": 0.02}
    assert "runner: local" in (run_dir / "mutate" / "rationale.md").read_text()
    assert not (run_dir / "mutate" / "predicted_fixes.json").exists()
