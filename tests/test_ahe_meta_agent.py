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
    spec = importlib.util.spec_from_file_location("ahe_under_test", ROOT / "library/meta_agent/ahe.py")
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
    (checkout / "evolve.yaml").write_text(
        "experiment:\n  id: ahe\n"
        "surface:\n  include:\n    - target/**\n  exclude: []\n"
        "operators:\n  meta_agent: {variant: ahe, runner: harbor}\n"
        "evaluator:\n  engine: harbor\n  dataset: test\n"
    )
    feedback = run_dir / "feedback"
    feedback.mkdir(parents=True)
    (feedback / "index.md").write_text("# Evidence\n\ntool error was not recovered\n")
    analysis = run_dir / "trace_analyzer" / "analysis"
    analysis.mkdir(parents=True)
    (analysis / "overview.md").write_text("# AHE Debugger Overview\n\nOVERVIEW ROOT CAUSE\n")
    detail = analysis / "detail"
    detail.mkdir()
    (detail / "task-a.md").write_text("DETAIL BODY MUST STAY ON DISK\n")
    (analysis / "change_evaluation.json").write_text(
        json.dumps({"status": "baseline" if parent == "0" else "evaluated", "transitions": {}})
    )
    evidence = run_dir / "trace_analyzer" / "evidence"
    evidence.mkdir()
    (evidence / "overview.json").write_text(json.dumps({"cases": [{"task_name": "task-a"}]}))
    workspace.mkdir(exist_ok=True)
    (workspace / "archive.jsonl").write_text('{"genid":"0","score":0}\n')
    if parent != "0":
        prior = workspace / "runs" / f"gen-{parent}" / "meta_agent"
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
        "KEEP",
        "REVISE",
        "ROLLBACK + PIVOT",
        "Current debugger reports evaluate the selected parent",
        "<AHE_CHANGE_MANIFEST>",
        "pass@1",
    ):
        assert required in prompt
    assert "OVERVIEW ROOT CAUSE" in prompt
    assert "DETAIL BODY MUST STAY ON DISK" not in prompt
    assert f"runs/gen-{ctx.genid}/trace_analyzer/analysis/detail/" in prompt
    assert f"runs/gen-{ctx.genid}/trace_analyzer/evidence/cases.jsonl" in prompt
    assert f"runs/gen-{ctx.genid}/rollout/" in prompt
    assert str(ctx.run_dir) not in prompt


def test_ahe_prompt_requires_nonempty_overview(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)
    (ctx.run_dir / "trace_analyzer/analysis/overview.md").write_text("")

    with pytest.raises(RuntimeError, match="empty AHE debugger overview"):
        module.build_prompt(checkout, "fallback", ctx)


def test_ahe_meta_agent_requires_valid_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)

    def fake_run_agent(root: Path, prompt: str, actual_ctx: OperatorContext):
        assert root == checkout and actual_ctx == ctx and "fallback" not in prompt
        source = root / "target/src/minisweagent/agents/default.py"
        source.write_text(source.read_text() + "RETRY_TOOL_ERRORS = True\n")
        return SimpleNamespace(output=_output(_manifest()), usage={"usd": 0.1})

    monkeypatch.setattr(module, "run_agent", fake_run_agent)
    result = module.AheMetaAgent().run(checkout, "fallback", ctx)

    assert result.changed == ["target/src/minisweagent/agents/default.py"]
    assert "change-manifest: parsed" in result.notes
    assert json.loads((run_dir / "meta_agent/change_manifest.json").read_text()) == _manifest()


def test_ahe_invalid_manifest_fails_after_preserving_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)

    def fake_run_agent(root: Path, _prompt: str, _ctx: OperatorContext):
        source = root / "target/src/minisweagent/agents/default.py"
        source.write_text(source.read_text() + "RETRY_TOOL_ERRORS = True\n")
        return SimpleNamespace(output="edited without manifest", usage={"usd": 0.1})

    monkeypatch.setattr(module, "run_agent", fake_run_agent)
    with pytest.raises(ValueError, match="exactly one"):
        module.AheMetaAgent().run(checkout, "fallback", ctx)
    for name in ("output.txt", "patch.diff", "changed.json", "surface-check.json", "usage.json"):
        assert (run_dir / "meta_agent" / name).is_file()


def test_ahe_runner_failure_preserves_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)

    def fail(*_args, **_kwargs):
        raise AgentCommandError("failed", output="runner output", returncode=7, usage={"usd": 0.2})

    monkeypatch.setattr(module, "run_agent", fail)
    with pytest.raises(SystemExit, match="7"):
        module.AheMetaAgent().run(checkout, "fallback", ctx)
    assert (run_dir / "meta_agent/output.txt").read_text() == "runner output"
    assert json.loads((run_dir / "meta_agent/usage.json").read_text()) == {"usd": 0.2}
