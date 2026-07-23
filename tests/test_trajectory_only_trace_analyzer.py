import importlib.util
import json
import random
from pathlib import Path
from types import SimpleNamespace

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "library" / "trace_analyzer" / "trajectory_only.py"
    spec = importlib.util.spec_from_file_location("evolve_test_trajectory_only", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_trajectory_only_runs_separate_behavior_judge_and_exposes_one_selected_view(
    tmp_path: Path, monkeypatch
) -> None:
    module = _module()
    checkout = tmp_path / "checkout"
    run_dir = checkout / "runs" / "gen-1"
    rollout = run_dir / "rollout"
    rollout.mkdir(parents=True)
    (rollout / "cases.json").write_text(
        json.dumps(
            [
                {
                    "task_name": "terminal/task-a",
                    "outcome": "failed",
                    "reward": 0,
                    "instruction": "ground-truth task text",
                    "verifier_output": "ground-truth verifier failure",
                    "trajectory_events": [
                        {
                            "type": "tool_call",
                            "name": "exec",
                            "arguments": {"cmd": "pytest -q"},
                        },
                        {
                            "type": "tool_result",
                            "observation": "ERROR: one test failed",
                        },
                    ],
                }
            ]
        )
    )
    ctx = OperatorContext(
        workspace=checkout,
        checkout=checkout,
        run_dir=run_dir,
        genid="1",
        parent=None,
        round=None,
        fan_out=1,
        config={"judge_retry_attempts": 1, "judge_max_concurrent": 1},
        rng=random.Random(0),
    )
    monkeypatch.setattr(module, "_runner_config", lambda _checkout: {"agent": "codex", "model": "gpt-test"})
    prompts = []

    def fake_judge(_checkout, prompt, _ctx, **_kwargs):
        prompts.append(prompt)
        return SimpleNamespace(
            output=json.dumps(
                {
                    "score": 2,
                    "category": "software-engineering",
                    "outcome": "The test run failed.",
                    "failure_reason": "The agent did not repair the failing test.",
                }
            ),
            usage={"usd": 0.01},
        )

    monkeypatch.setattr(module, "run_readonly_agent", fake_judge)

    result = module.TrajectoryOnly().analyze(checkout, ctx)

    assert len(prompts) == 1
    assert "pytest -q" in prompts[0]
    assert "one test failed" in prompts[0]
    assert "ground-truth task text" not in prompts[0]
    assert "ground-truth verifier failure" not in prompts[0]
    selected = (run_dir / "trace_analyzer" / "evidence" / "selected.md").read_text()
    assert selected.count("### Agent Behavior Analysis (this batch)") == 1
    assert '"score": 2' in selected
    assert "ground-truth" not in selected
    assert result.summary["judge_verdicts"] == 1
    assert not (run_dir / "trace_analyzer" / "evidence" / "raw_traces.jsonl").exists()
