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
    path = ROOT / "library" / "mutate" / "gepa.py"
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
    (checkout / "program.md").write_text("protected\n")
    (checkout / "evolve.yaml").write_text(
        "experiment:\n  id: gepa\n"
        "surface:\n  include:\n    - target/**\n  exclude: []\n"
        "operators:\n  mutate: {variant: gepa}\n"
        "evaluator:\n  engine: harbor\n  dataset: test\n"
    )
    evidence = run_dir / "analyze/evidence"
    evidence.mkdir(parents=True)
    evidence.joinpath("reflective_dataset.json").write_text(
        json.dumps(
            {
                "prompt": [{"Inputs": {"task_id": "a"}, "Feedback": {"outcome": "failed"}}],
                "skill": [{"Inputs": {"task_id": "a"}, "Feedback": {"outcome": "failed"}}],
            }
        )
    )
    reflection = evidence / "reflection"
    reflection.mkdir()
    reflection.joinpath("00-prompt.json").write_text(
        json.dumps([{"Inputs": {"task_id": "a"}, "Feedback": {"outcome": "failed"}}])
    )
    reflection.joinpath("01-skill.json").write_text(
        json.dumps([{"Inputs": {"task_id": "a"}, "Feedback": {"outcome": "failed"}}])
    )
    evidence.joinpath("manifest.json").write_text(
        json.dumps(
            {
                "selected_variant": "gepa",
                "component_evidence": {
                    "prompt": {
                        "file": "reflection/00-prompt.json",
                        "paths": ["target/prompt.md"],
                        "records": 1,
                    },
                    "skill": {
                        "file": "reflection/01-skill.json",
                        "paths": ["target/skills/task-execution"],
                        "records": 1,
                    },
                },
            }
        )
    )
    workspace.mkdir(exist_ok=True)
    handoff = workspace / "artifacts" / "generations" / "0" / "handoff.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("GEPA HANDOFF BODY MUST STAY ON DISK\n")
    _git(checkout, "init", "-q")
    _git(checkout, "config", "user.name", "test")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-qm", "parent")
    _git(checkout, "tag", "gen/0")
    config = {
        "runner": "harbor",
        "components": {"prompt": "target/prompt.md", "skill": "target/skills/task-execution"},
        "component_strategy": "round_robin",
    }
    ctx = OperatorContext(workspace, checkout, run_dir, "1", "0", None, 1, config, random.Random(0))
    return checkout, run_dir, ctx


def test_gepa_mutate_reads_file_evidence_and_edits_live_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, run_dir, ctx = _case(tmp_path)

    def fake_run(root: Path, prompt: str, _ctx: OperatorContext):
        assert "assertion" not in prompt
        assert "`prompt`" in prompt
        assert "{{ instruction }}" in prompt
        assert "selected parent's handoff" in prompt
        assert "/app/task/workspace/artifacts/generations/0/handoff.md" in prompt
        assert "/app/task/workspace/artifacts/generations/1" in prompt
        assert "GEPA HANDOFF BODY MUST STAY ON DISK" not in prompt
        assert "You CAN modify any file under `target/`" in prompt
        assert "This method does not impose a narrower per-proposal path scope." in prompt
        assert "Runtime prompt/config: `target/prompt.md`" in prompt
        assert "Feedback.natural_language_feedback" in prompt
        assert "a quality score and must not replace" in prompt
        assert "/app/task/workspace/runs/gen-1/analyze/evidence/manifest.json" in prompt
        assert "/app/task/workspace/runs/gen-1/analyze/evidence/reflection/00-prompt.json" in prompt
        assert '"task_id": "a"' not in prompt
        assert "Solve: {{ instruction }}" not in prompt
        (root / "target/prompt.md").write_text("Be systematic. Solve: {{ instruction }}\n")
        return SimpleNamespace(output="edited", usage={"usd": 0.1})

    monkeypatch.setattr(module, "run_agent", fake_run)
    result = module.GepaMutate().mutate(checkout, "unused", ctx)

    assert result.changed == ["target/prompt.md"]
    proposal = json.loads((run_dir / "mutate/proposal.json").read_text())
    assert proposal["components"] == ["prompt"]
    assert proposal["example_counts"] == {"prompt": 1}
    assert proposal["evidence_files"] == {"prompt": "runs/gen-1/analyze/evidence/reflection/00-prompt.json"}


def test_gepa_mutate_allows_changes_outside_focus_within_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)

    def fake_run(root: Path, _prompt: str, _ctx: OperatorContext):
        (root / "target/skills/task-execution/SKILL.md").write_text("unselected change\n")
        return SimpleNamespace(output="edited", usage={"usd": 0})

    monkeypatch.setattr(module, "run_agent", fake_run)
    result = module.GepaMutate().mutate(checkout, "unused", ctx)

    assert result.changed == ["target/skills/task-execution/SKILL.md"]


def test_gepa_skill_component_can_add_bundled_resource(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, run_dir, original = _case(tmp_path)
    ctx = OperatorContext(
        original.workspace,
        checkout,
        run_dir,
        "2",
        original.parent,
        original.round,
        original.fan_out,
        original.config,
        random.Random(0),
    )

    def fake_run(root: Path, prompt: str, _ctx: OperatorContext):
        assert "`target/skills/task-execution`" in prompt
        assert "component path is a skill directory" in prompt
        assert "bundled behavior resources" in prompt
        references = root / "target/skills/task-execution/references"
        references.mkdir()
        references.joinpath("verification.md").write_text("Run focused verification before submission.\n")
        return SimpleNamespace(output="added reference", usage={"usd": 0})

    monkeypatch.setattr(module, "run_agent", fake_run)
    result = module.GepaMutate().mutate(checkout, "unused", ctx)

    assert result.changed == ["target/skills/task-execution/references/"]
    assert (checkout / "target/skills/task-execution/references/verification.md").is_file()
    proposal = json.loads((run_dir / "mutate/proposal.json").read_text())
    assert proposal["components"] == ["skill"]
    assert proposal["paths"] == ["target/skills/task-execution"]


def test_gepa_mutate_rejects_changes_outside_mutable_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)

    def fake_run(root: Path, _prompt: str, _ctx: OperatorContext):
        (root / "program.md").write_text("changed\n")
        return SimpleNamespace(output="edited", usage={"usd": 0})

    monkeypatch.setattr(module, "run_agent", fake_run)
    with pytest.raises(SystemExit, match="outside the mutable surface"):
        module.GepaMutate().mutate(checkout, "unused", ctx)
