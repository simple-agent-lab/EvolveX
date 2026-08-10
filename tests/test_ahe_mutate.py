import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from evolve.agent import AgentCommandError
from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("ahe_under_test", ROOT / "library/mutate/ahe.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> None:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def _case(tmp_path: Path, *, genid: str = "1", parent: str = "0"):
    workspace = tmp_path / "workspace"
    checkout = tmp_path / "checkout"
    run_dir = workspace / "runs" / f"gen-{genid}"
    source = checkout / "target/src/minisweagent/agents/default.py"
    source.parent.mkdir(parents=True)
    source.write_text("STEP_LIMIT = 10\n")
    prompt = checkout / "target/src/minisweagent/config/mini.yaml"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("agent:\n  system_template: helpful\n")
    (checkout / "evolve.yaml").write_text(
        "experiment:\n  id: ahe\n"
        "surface:\n  include:\n    - target/**\n  exclude: []\n"
        "operators:\n  mutate: {operator: ahe, timeout_s: 600, config: {runner: harbor}}\n"
        "evaluator:\n  engine: harbor\n  dataset: test\n"
    )
    feedback = run_dir / "feedback"
    feedback.mkdir(parents=True)
    (feedback / "index.md").write_text("# Evidence\n\ntool error was not recovered\n")
    analysis = run_dir / "analyze" / "analysis"
    analysis.mkdir(parents=True)
    (analysis / "overview.md").write_text("# AHE Debugger Overview\n\nOVERVIEW ROOT CAUSE\n")
    detail = analysis / "detail"
    detail.mkdir()
    (detail / "task-a.md").write_text("DETAIL BODY MUST STAY ON DISK\n")
    (analysis / "change_evaluation.json").write_text(
        json.dumps(
            {
                "status": "baseline" if parent == "0" else "evaluated",
                "transitions": {},
                "sentinel": "ATTRIBUTION BODY MUST STAY ON DISK",
            }
        )
    )
    evidence = run_dir / "analyze" / "evidence"
    evidence.mkdir()
    (evidence / "overview.json").write_text(json.dumps({"cases": [{"task_name": "task-a"}]}))
    workspace.mkdir(exist_ok=True)
    (workspace / "archive.jsonl").write_text('{"genid":"0","score":0,"sentinel":"ARCHIVE BODY MUST STAY ON DISK"}\n')
    handoff = workspace / "artifacts" / "generations" / parent / "handoff.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("PARENT HANDOFF BODY MUST STAY ON DISK\n")
    if parent != "0":
        prior = workspace / "runs" / f"gen-{parent}" / "mutate"
        prior.mkdir(parents=True, exist_ok=True)
        (prior / "change_manifest.json").write_text(json.dumps({"decision": "revise"}))
    _git(checkout, "init", "-q")
    _git(checkout, "config", "user.name", "test")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-qm", "parent")
    _git(checkout, "tag", f"gen/{parent}")
    ctx = OperatorContext(workspace, checkout, run_dir, genid, parent, None, 1, {"runner": "harbor"}, random.Random(0))
    return checkout, run_dir, ctx


def _manifest(genid: str = "1", parent: str = "0") -> dict:
    del parent
    return {
        "iteration": int(genid),
        "changes": [
            {
                "id": "chg-1",
                "type": "improvement",
                "description": "Retry transient tool failures",
                "files": ["target/src/minisweagent/agents/default.py"],
                "failure_pattern": "tool errors terminate the attempt",
                "predicted_fixes": ["task-a"],
                "risk_tasks": [],
                "constraint_level": "middleware",
                "why_this_component": "the retry belongs in execution control flow",
            }
        ],
    }


def _output(manifest: dict) -> str:
    return "edited\n<AHE_CHANGE_MANIFEST>\n" + json.dumps(manifest) + "\n</AHE_CHANGE_MANIFEST>\n"


def test_ahe_manifest_extraction_and_validation(tmp_path: Path) -> None:
    module = _module()
    manifest = _manifest()
    assert module._extract_manifest(_output(manifest), "1") == manifest
    with pytest.raises(ValueError, match="exactly one"):
        module._extract_manifest("no manifest", "1")
    stale = _manifest()
    stale["iteration"] = 9
    with pytest.raises(ValueError, match="iteration"):
        module._extract_manifest(_output(stale), "1")
    empty = _manifest()
    empty["changes"] = []
    with pytest.raises(ValueError, match="changes"):
        module._extract_manifest(_output(empty), "1")


def test_ahe_prompt_uses_official_decisions_and_required_manifest(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)
    prompt = module.build_prompt(checkout, "fallback", ctx)
    for required in (
        "configured candidate harness",
        "declared mutable surface",
        "Identify the active execution path",
        "KEEP",
        "REVISE",
        "ROLLBACK + PIVOT",
        "Current debugger reports evaluate the selected parent",
        "target/.ahe-change-manifest.json",
        "before the submission action",
        "pass@1",
        "deployed benchmark-solving harness",
        "not available inside benchmark episodes",
        "Do not copy this evolution workflow",
        "Do not refer to debuggers",
        "You CAN modify any file under `target/`",
        "Runtime prompt/config: `target/src/minisweagent/config/mini.yaml`",
        "This method further restricts the current proposal to: `target`",
    ):
        assert required in prompt
    for forbidden in (
        "Improve the MiniSWE harness",
        "Make one coherent target/** change",
        "runs the target's `DefaultAgent` with the `mini` configuration",
        "Benchmark-specific configurations are inactive",
    ):
        assert forbidden not in prompt
    assert "Evidence reading order" in prompt
    assert "OVERVIEW ROOT CAUSE" not in prompt
    assert "ATTRIBUTION BODY MUST STAY ON DISK" not in prompt
    assert "ARCHIVE BODY MUST STAY ON DISK" not in prompt
    assert "DETAIL BODY MUST STAY ON DISK" not in prompt
    assert "/app/task/workspace/runs/gen-1/analyze/analysis/overview.md" in prompt
    assert "/app/task/workspace/runs/gen-1/analyze/analysis/change_evaluation.json" in prompt
    assert "/app/task/workspace/runs/gen-1/analyze/analysis/detail" in prompt
    assert "/app/task/workspace/runs/gen-1/analyze/evidence/cases.jsonl" in prompt
    assert "/app/task/workspace/runs/gen-1/rollout" in prompt
    assert "No selected-parent meta-agent change exists for this baseline generation." in prompt
    assert str(ctx.run_dir) not in prompt
    assert "Repository: /app/task/workspace" in prompt
    assert "Archive: /app/task/workspace/archive.jsonl" in prompt
    assert "Raw trace evidence: /app/task/workspace/runs/gen-1/analyze/evidence" in prompt
    assert "selected parent's handoff" in prompt


def test_ahe_prompt_describes_codex_plugin_target_when_present(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)
    (checkout / "target" / "codex.toml").write_text('[codex]\nmodel = "gpt-5.4"\n')
    prompt = module.build_prompt(checkout, "fallback", ctx)
    normalized = " ".join(prompt.split())

    assert "Improve the Codex harness" in prompt
    assert "local plugin under `target/plugins/`" in prompt
    assert "candidate plugin" in normalized
    assert "temporary Codex home" in normalized
    assert "Improve the MiniSWE harness" not in prompt
    assert "target's `DefaultAgent`" not in prompt
    assert "/app/task/workspace/artifacts/generations/0/handoff.md" in prompt
    assert "/app/task/workspace/artifacts/generations/1" in prompt
    assert "PARENT HANDOFF BODY MUST STAY ON DISK" not in prompt
    assert "delimited official-style" not in prompt


def test_ahe_prompt_does_not_require_readable_evidence_bodies(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)
    (ctx.run_dir / "analyze/analysis/overview.md").write_text("")
    (ctx.run_dir / "analyze/analysis/change_evaluation.json").unlink()

    prompt = module.build_prompt(checkout, "fallback", ctx)

    assert "/app/task/workspace/runs/gen-1/analyze/analysis/overview.md" in prompt
    assert "/app/task/workspace/runs/gen-1/analyze/analysis/change_evaluation.json" in prompt


def test_ahe_mutate_requires_valid_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)

    def fake_run_agent(root: Path, prompt: str, actual_ctx: OperatorContext):
        assert root == checkout and actual_ctx == ctx and "fallback" not in prompt
        source = root / "target/src/minisweagent/agents/default.py"
        source.write_text(source.read_text() + "RETRY_TOOL_ERRORS = True\n")
        (root / "target/.ahe-change-manifest.json").write_text(json.dumps(_manifest()))
        return SimpleNamespace(output="edited", usage={"usd": 0.1})

    monkeypatch.setattr(module, "run_agent", fake_run_agent)
    result = module.AheMutate().mutate(checkout, "fallback", ctx)

    assert result.changed == ["target/src/minisweagent/agents/default.py"]
    assert "change-manifest: parsed" in result.notes
    assert json.loads((run_dir / "mutate/change_manifest.json").read_text()) == _manifest()
    assert not (checkout / "target/.ahe-change-manifest.json").exists()


def test_ahe_invalid_manifest_fails_after_preserving_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)

    def fake_run_agent(root: Path, _prompt: str, _ctx: OperatorContext):
        source = root / "target/src/minisweagent/agents/default.py"
        source.write_text(source.read_text() + "RETRY_TOOL_ERRORS = True\n")
        return SimpleNamespace(output="edited without manifest", usage={"usd": 0.1})

    monkeypatch.setattr(module, "run_agent", fake_run_agent)
    with pytest.raises(ValueError, match="manifest file"):
        module.AheMutate().mutate(checkout, "fallback", ctx)
    for name in ("output.txt", "patch.diff", "changed.json", "surface-check.json", "usage.json"):
        assert (run_dir / "mutate" / name).is_file()


def test_ahe_prompt_points_to_prior_change_without_inlining_it(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path, genid="2", parent="1")
    prior = ctx.workspace / "runs/gen-1/mutate"
    (prior / "output.txt").write_text("PREVIOUS REASONING BODY")
    (prior / "changed.json").write_text('["target/previous.py"]')
    (prior / "patch.diff").write_text("PREVIOUS PATCH BODY")

    prompt = module.build_prompt(checkout, "fallback", ctx)

    assert "Selected parent meta-agent artifacts" in prompt
    assert "/app/task/workspace/runs/gen-1/mutate" in prompt
    assert "PREVIOUS REASONING BODY" not in prompt
    assert "target/previous.py" not in prompt
    assert "PREVIOUS PATCH BODY" not in prompt
    assert "No selected-parent meta-agent change exists" not in prompt


def test_ahe_prompt_accepts_fanout_generation_ids(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path, genid="2-child-a", parent="1")

    prompt = module.build_prompt(checkout, "fallback", ctx)

    assert '"iteration": "2-child-a"' in prompt


def test_ahe_runner_failure_preserves_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)

    def fail(*_args, **_kwargs):
        raise AgentCommandError("failed", output="runner output", returncode=7, usage={"usd": 0.2})

    monkeypatch.setattr(module, "run_agent", fail)
    with pytest.raises(SystemExit, match="7"):
        module.AheMutate().mutate(checkout, "fallback", ctx)
    assert (run_dir / "mutate/output.txt").read_text() == "runner output"
    assert json.loads((run_dir / "mutate/usage.json").read_text()) == {"usd": 0.2}
