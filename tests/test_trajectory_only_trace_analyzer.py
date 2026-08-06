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


def test_trajectory_judge_rejects_non_finite_scores() -> None:
    module = _module()

    for score in ("NaN", "Infinity", "-Infinity"):
        try:
            module._json_object(f'{{"score": {score}}}')
        except ValueError as exc:
            assert "required JSON object" in str(exc)
        else:
            raise AssertionError(f"non-finite score was accepted: {score}")


def test_trajectory_judge_submission_prompt_uses_exact_installed_agent_identity() -> None:
    module = _module()
    record = {"task_id": "task-a", "compressed_trajectory": "ran tests"}

    installed = module._runner_prompt(
        record, {"agent": "evolve.integrations.harbor.miniswe_task_file:InstalledMiniSweAgent"}
    )
    generic = module._runner_prompt(record, {"agent": "custom:FileTaskMiniSweAgent"})

    assert "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" in installed
    assert "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" not in generic


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
    monkeypatch.setattr(
        module,
        "_runner_config",
        lambda _checkout, _config: {"agent": "codex", "model": "gpt-test"},
    )
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


def test_trajectory_judge_can_use_a_separate_modelhub_environment(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(
        module,
        "operator_blocks",
        lambda _checkout: {
            "meta_agent": {
                "agent": "codex",
                "model": "gpt-5.4",
                "agent_kwargs": {"reasoning_effort": "xhigh"},
            }
        },
    )
    monkeypatch.setenv("OPENAI_API_KEY", "target-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://target.example/v1")
    monkeypatch.setenv("EVOLVE_JUDGE_OPENAI_API_KEY", "judge-key")
    monkeypatch.setenv("EVOLVE_JUDGE_OPENAI_BASE_URL", "http://judge.example/v1")
    monkeypatch.setenv("EVOLVE_JUDGE_OPENAI_API_BASE", "http://judge.example/v1")

    config = module._runner_config(
        tmp_path,
        {
            "judge_agent": "evolve_harbor_adapter:ResponsesCodexAgent",
            "judge_agent_kwargs": {"reasoning_effort": "high"},
            "judge_model": "gpt-5.4-mini-2026-03-17",
            "judge_inherit_openai_credentials": True,
        },
    )

    assert config["agent"] == "evolve_harbor_adapter:ResponsesCodexAgent"
    assert config["model"] == "gpt-5.4-mini-2026-03-17"
    assert config["agent_kwargs"] == {"reasoning_effort": "high"}
    assert config["agent_env"] == {
        "OPENAI_API_KEY": "judge-key",
        "OPENAI_BASE_URL": "http://judge.example/v1",
        "OPENAI_API_BASE": "http://judge.example/v1",
    }


def test_trajectory_only_passes_runtime_failure_observation_to_judge(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    checkout = tmp_path / "checkout"
    run_dir = checkout / "runs" / "gen-1"
    rollout = run_dir / "rollout"
    rollout.mkdir(parents=True)
    (rollout / "cases.json").write_text(
        json.dumps(
            [
                {
                    "task_name": "terminal/task-infra",
                    "outcome": "infra_error",
                    "reward": None,
                    "exception": {
                        "type": "ModelProviderError",
                        "message": "No tool output found for function call call-1",
                    },
                    "trajectory_events": [],
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
    monkeypatch.setattr(
        module,
        "_runner_config",
        lambda _checkout, _config: {"agent": "codex", "model": "gpt-test"},
    )
    prompts = []

    def fake_judge(_checkout, prompt, _ctx, **_kwargs):
        prompts.append(prompt)
        return SimpleNamespace(
            output='{"score": 0, "category": "runtime", "outcome": "runtime failed", "failure_reason": "tool history"}',
            usage={},
        )

    monkeypatch.setattr(module, "run_readonly_agent", fake_judge)

    result = module.TrajectoryOnly().analyze(checkout, ctx)

    assert result.summary["cases"] == 1
    assert "No tool output found for function call call-1" in prompts[0]
    selected = (run_dir / "trace_analyzer/evidence/selected.md").read_text()
    assert "tool history" in selected
    assert "infra_error" not in selected
