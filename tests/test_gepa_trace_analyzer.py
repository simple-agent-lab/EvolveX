import importlib.util
import json
import random
from pathlib import Path

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "library" / "trace_analyzer" / "gepa.py"
    spec = importlib.util.spec_from_file_location("gepa_trace_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gepa_trace_analyzer_builds_component_reflective_dataset(tmp_path: Path) -> None:
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
            "events": [{"type": "tool_call", "name": "exec"}],
            "tool_calls": [{"name": "exec", "arguments": "pytest"}],
            "observations": ["failed"],
            "verifier_output": "assertion failed",
            "exception": {},
        },
        {"task_name": "task-b", "reward": None, "outcome": "infra_error"},
    ]
    (rollout / "cases.json").write_text(json.dumps(cases))
    components = {"prompt": "target/prompt.md", "skill": "target/skills/task/SKILL.md"}
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

    result = module.GepaTraceAnalyzer().analyze(tmp_path, ctx)

    dataset = json.loads((run_dir / "trace_analyzer/evidence/reflective_dataset.json").read_text())
    assert list(dataset) == ["prompt", "skill"]
    assert len(dataset["prompt"]) == len(dataset["skill"]) == 1
    record = dataset["prompt"][0]
    assert record["Inputs"] == {"instruction": "Fix A", "task_id": "task-a"}
    assert record["Generated Outputs"]["ordered_events"][0]["name"] == "exec"
    assert record["Feedback"]["verifier_output"] == "assertion failed"
    assert record["Scores (Higher is Better)"] == {"reward": 0.0}
    assert result.summary["usable_cases"] == 1
