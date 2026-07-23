import importlib.util
import json
import random
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "library" / "meta_agent" / "gepa.py"
    spec = importlib.util.spec_from_file_location("gepa_meta_under_test", path)
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
    skill = checkout / "target/skills/task-execution/SKILL.md"
    skill.parent.mkdir(parents=True)
    (checkout / "target/prompt.md").write_text("Solve: {{ instruction }}\n")
    skill.write_text("Inspect, edit, test.\n")
    (checkout / "evolve.yaml").write_text(
        "experiment:\n  id: gepa\n"
        "surface:\n  include:\n    - target/**\n  exclude: []\n"
        "operators:\n  meta_agent: {variant: gepa}\n"
        "evaluator:\n  engine: harbor\n  dataset: test\n"
    )
    evidence = run_dir / "trace_analyzer/evidence"
    evidence.mkdir(parents=True)
    evidence.joinpath("reflective_dataset.json").write_text(
        json.dumps(
            {
                "prompt": [{"Inputs": {"task_id": "a"}, "Feedback": {"outcome": "failed"}}],
                "skill": [{"Inputs": {"task_id": "a"}, "Feedback": {"outcome": "failed"}}],
            }
        )
    )
    workspace.mkdir(exist_ok=True)
    _git(checkout, "init", "-q")
    _git(checkout, "config", "user.name", "test")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-qm", "parent")
    _git(checkout, "tag", "gen/0")
    config = {
        "runner": "harbor",
        "components": {"prompt": "target/prompt.md", "skill": "target/skills/task-execution/SKILL.md"},
        "component_strategy": "round_robin",
    }
    ctx = OperatorContext(workspace, checkout, run_dir, "1", "0", None, 1, config, random.Random(0))
    return checkout, run_dir, ctx


def test_gepa_meta_agent_edits_only_selected_component(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)

    def fake_run(root: Path, prompt: str, _ctx: OperatorContext):
        assert "assertion" not in prompt
        assert "`prompt`" in prompt
        assert "{{ instruction }}" in prompt
        assert "You CAN modify any file under `target/`" in prompt
        assert "This method further restricts the current proposal to: `target/prompt.md`" in prompt
        assert "Runtime prompt/config: `target/prompt.md`" in prompt
        (root / "target/prompt.md").write_text("Be systematic. Solve: {{ instruction }}\n")
        return SimpleNamespace(output="edited", usage={"usd": 0.1})

    monkeypatch.setattr(module, "run_agent", fake_run)
    result = module.GepaMetaAgent().run(checkout, "unused", ctx)

    assert result.changed == ["target/prompt.md"]
    proposal = json.loads((run_dir / "meta_agent/proposal.json").read_text())
    assert proposal["components"] == ["prompt"]
    assert proposal["example_counts"] == {"prompt": 1}
    assert json.loads((run_dir / "meta_agent/component-scope-check.json").read_text()) == {
        "ok": True,
        "violations": [],
    }


def test_gepa_meta_agent_rejects_changes_outside_component(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)

    def fake_run(root: Path, _prompt: str, _ctx: OperatorContext):
        (root / "target/skills/task-execution/SKILL.md").write_text("unselected change\n")
        return SimpleNamespace(output="edited", usage={"usd": 0})

    monkeypatch.setattr(module, "run_agent", fake_run)
    with pytest.raises(SystemExit, match="outside the selected component"):
        module.GepaMetaAgent().run(checkout, "unused", ctx)
