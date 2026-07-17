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
    spec = importlib.util.spec_from_file_location("ahe_under_test", ROOT / "library/meta_agent/ahe.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> None:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def _case(tmp_path: Path):
    workspace = tmp_path / "workspace"
    checkout = tmp_path / "checkout"
    run_dir = workspace / "runs/gen-1"
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
    workspace.mkdir(exist_ok=True)
    (workspace / "archive.jsonl").write_text('{"genid":"0","score":0}\n')
    _git(checkout, "init", "-q")
    _git(checkout, "config", "user.name", "test")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-qm", "parent")
    _git(checkout, "tag", "gen/0")
    ctx = OperatorContext(workspace, checkout, run_dir, "1", "0", None, 1, {"runner": "harbor"}, random.Random(0))
    return checkout, run_dir, ctx


def test_ahe_prompt_and_shared_runner_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)

    def fake_run_agent(root: Path, prompt: str, actual_ctx: OperatorContext):
        assert root == checkout and actual_ctx == ctx
        assert "tool error was not recovered" in prompt
        assert "inspect relevant MiniSWE source" in prompt
        assert "one coherent harness change" in prompt
        source = root / "target/src/minisweagent/agents/default.py"
        source.write_text(source.read_text() + "RETRY_TOOL_ERRORS = True\n")
        report = run_dir / "meta_agent/ahe-report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"hypothesis": "retry transient tool failures"}))
        return SimpleNamespace(output="edited", usage={"usd": 0.1})

    monkeypatch.setattr(module, "run_agent", fake_run_agent)
    result = module.AheMetaAgent().run(checkout, "fallback", ctx)
    assert result.changed == ["target/src/minisweagent/agents/default.py"]
    assert {"variant: ahe", "runner: harbor", "ahe-report: preserved"} <= set(result.notes)
    assert (run_dir / "meta_agent/patch.diff").is_file()
    assert not (run_dir / "meta_agent/predicted_fixes.json").exists()


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
