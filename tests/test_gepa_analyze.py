import importlib.util
import json
import random
from pathlib import Path

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "library" / "analyze" / "gepa.py"
    spec = importlib.util.spec_from_file_location("gepa_trace_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gepa_analyze_builds_component_reflective_dataset(tmp_path: Path) -> None:
    module = _module()
    run_dir = tmp_path / "runs/gen-1"
    rollout = run_dir / "rollout"
    rollout.mkdir(parents=True)
    cases = [
        {
            "task_name": "task-a",
            "reward": 0,
            "outcome": "failed",
            "instruction": "Fix A",
            "agent_messages": ["trying"],
            "events": [{"type": "tool_call", "name": "legacy"}],
            "trajectory_events": [
                {"type": "agent_message", "message": "start"},
                {"type": "tool_call", "name": "exec"},
            ],
            "tool_calls": [{"name": "exec", "arguments": "pytest"}],
            "observations": ["failed"],
            "feedback": {"message": "The visual hierarchy is clear; reduce template-like decoration."},
            "verifier_output": "assertion failed",
            "exception": {},
        },
        {"task_name": "task-b", "reward": None, "outcome": "infra_error"},
    ]
    (rollout / "cases.json").write_text(json.dumps(cases))
    components = {"prompt": "target/prompt.md", "skill": "target/skills/task"}
    ctx = OperatorContext(
        workspace=tmp_path,
        checkout=tmp_path,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={"components": components},
        rng=random.Random(0),
    )

    result = module.GepaAnalyze().analyze(tmp_path, ctx)

    dataset = json.loads((run_dir / "analyze/evidence/reflective_dataset.json").read_text())
    assert list(dataset) == ["prompt", "skill"]
    assert len(dataset["prompt"]) == len(dataset["skill"]) == 2
    record = dataset["prompt"][0]
    assert record["Inputs"] == {"instruction": "Fix A", "task_id": "task-a"}
    assert record["Generated Outputs"]["ordered_events"] == [
        {"message": "start", "type": "agent_message"},
        {"name": "exec", "type": "tool_call"},
    ]
    assert record["Feedback"]["verifier_output"] == "assertion failed"
    assert record["Feedback"]["natural_language_feedback"] == {
        "message": "The visual hierarchy is clear; reduce template-like decoration."
    }
    assert record["Scores (Higher is Better)"] == {"reward": 0.0}
    infra_record = dataset["prompt"][1]
    assert infra_record["Inputs"]["task_id"] == "task-b"
    assert infra_record["Feedback"]["outcome"] == "infra_error"
    manifest = json.loads((run_dir / "analyze/evidence/manifest.json").read_text())
    assert manifest["component_evidence"] == {
        "prompt": {"file": "reflection/00-prompt.json", "paths": ["target/prompt.md"], "records": 2},
        "skill": {"file": "reflection/01-skill.json", "paths": ["target/skills/task"], "records": 2},
    }
    prompt_records = json.loads((run_dir / "analyze/evidence/reflection/00-prompt.json").read_text())
    assert prompt_records == dataset["prompt"]
    assert "analyze/evidence/reflection/00-prompt.json" in result.artifacts
    assert result.summary["usable_cases"] == 2
    selected = (run_dir / "analyze/evidence/selected.md").read_text()
    assert "The visual hierarchy is clear; reduce template-like decoration." in selected
