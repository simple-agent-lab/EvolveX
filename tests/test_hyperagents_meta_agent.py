import importlib.util
import json
import random
import subprocess
from pathlib import Path
from types import SimpleNamespace

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _load_hyperagents_meta_agent():
    spec = importlib.util.spec_from_file_location(
        "hyperagents_meta_agent_under_test",
        ROOT / "library" / "meta_agent" / "hyperagents.py",
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
    (workspace / "evolve.yaml").write_text(
        "experiment:\n  id: test\n  max_generations: 4\n"
        "target:\n  seed: builtin-dummy\n"
        "surface:\n  include:\n    - target/**\n    - operators/**\n  exclude: []\n"
        "operators:\n  meta_agent: {timeout_s: 30}\n"
        "evaluator:\n  engine: harbor\n  dataset: pass@k\n  agent: target.harbor_agent:MiniSweSourceAgent\n"
    )
    (checkout / "target").mkdir(parents=True)
    (checkout / "operators").mkdir()
    (checkout / "target" / "agent.py").write_text("print('parent')\n")
    (checkout / "operators" / "meta_agent.py").write_text("# parent mutation operator\n")
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
    module = _load_hyperagents_meta_agent()
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(run_dir.parents[1], checkout, run_dir)
    ctx.config["runner"] = "harbor"
    evidence = run_dir / "feedback" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "selected.md").write_text("SELECTED TRACE EVIDENCE\n")
    (run_dir / "feedback" / "index.md").write_text(
        "# Feedback Bundle\n\n- [selected trace evidence](evidence/selected.md)\n"
    )

    prompt = module.build_prompt(checkout, "fallback observation", ctx)

    assert module.PROMPT.startswith("# HyperAgents")
    assert "Repository: /app/workspace" in prompt
    assert "Archive: /app/workspace/archive.jsonl" in prompt
    assert "Prior generation artifacts: /app/workspace/runs" in prompt
    assert "Feedback bundle: /app/workspace/runs/gen-1/feedback" in prompt
    assert "Raw trace evidence: /app/workspace/runs/gen-1/trace_analyzer/evidence" in prompt
    assert "SELECTED TRACE EVIDENCE" in prompt
    assert "fallback observation" not in prompt
    assert "Iterations remaining after this proposal: 3" in prompt
    assert "Modify any part of the allowed codebase" in prompt
    assert "Strongly prefer a substantive `target/**`" in prompt
    assert "operator-only proposal is allowed" in prompt
    assert "must include at least one substantive `target/**` change" not in prompt
    assert "`operators/**` remains editable" in prompt
    assert "cosmetic target edits" in prompt
    assert "You are editing the MiniSWE source checkout under target/." not in prompt


def test_hyperagents_meta_agent_records_complete_patch_for_target_and_workflow_edits(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_hyperagents_meta_agent()
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(run_dir.parents[1], checkout, run_dir)

    def fake_run_agent(workspace: Path, prompt: str, ctx: OperatorContext):
        assert workspace == checkout
        assert ctx.config["runner"] == "local"
        assert "Modify any part of the allowed codebase" in prompt
        assert "observation" in prompt
        (workspace / "target" / "agent.py").write_text("print('child')\n")
        (workspace / "operators" / "meta_agent.py").write_text("# improved mutation operator\n")
        return SimpleNamespace(output="edited target and workflow", usage={"usd": 0.02})

    monkeypatch.setattr(module, "run_agent", fake_run_agent)

    result = module.HyperAgentsMetaAgent().run(checkout, "observation", ctx)

    assert set(result.changed) == {"target/agent.py", "operators/meta_agent.py"}
    diff = (run_dir / "meta_agent" / "model_patch.diff").read_text()
    assert "diff --git a/target/agent.py b/target/agent.py" in diff
    assert "diff --git a/operators/meta_agent.py b/operators/meta_agent.py" in diff
    assert (run_dir / "meta_agent" / "patch.diff").read_text() == diff
    assert json.loads((run_dir / "meta_agent" / "usage.json").read_text()) == {"usd": 0.02}
    assert "runner: local" in (run_dir / "meta_agent" / "rationale.md").read_text()
    assert not (run_dir / "meta_agent" / "predicted_fixes.json").exists()
