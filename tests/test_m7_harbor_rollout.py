import importlib.util
import json
from pathlib import Path

from conftest import init_workspace

from evolve.feedback import write_feedback_bundle

ROOT = Path(__file__).resolve().parents[1]


def _harbor_rollout_module():
    path = ROOT / "library" / "rollout" / "harbor.py"
    spec = importlib.util.spec_from_file_location("evolve_test_harbor_rollout", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_trial(
    jobs_dir: Path,
    *,
    name: str,
    reward: float | None,
    exception_type: str = "",
    exception_message: str = "",
) -> Path:
    trial = jobs_dir / name
    (trial / "agent").mkdir(parents=True)
    (trial / "verifier").mkdir()
    payload = {
        "trial_name": name,
        "task_name": f"harbor/{name}",
        "agent_result": {
            "n_input_tokens": 100,
            "n_cache_tokens": 40,
            "n_output_tokens": 20,
            "cost_usd": 0.01,
        },
        "verifier_result": {"rewards": {"reward": reward}} if reward is not None else None,
        "exception_info": (
            {"exception_type": exception_type, "exception_message": exception_message} if exception_type else None
        ),
        "agent_execution": {"started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:00:02Z"},
    }
    (trial / "result.json").write_text(json.dumps(payload))
    trajectory = {
        "steps": [
            {"source": "user", "message": "<environment_context>noise</environment_context>"},
            {"source": "user", "message": f"Fix task {name}."},
            {
                "source": "agent",
                "message": "I will inspect the failure.",
                "tool_calls": [{"function_name": "exec", "arguments": {"command": "run tests"}}],
                "observation": {"results": [{"content": "tests failed: missing output"}]},
            },
        ]
    }
    (trial / "agent" / "trajectory.json").write_text(json.dumps(trajectory))
    (trial / "verifier" / "test-stdout.txt").write_text("OPENAI_API_KEY=must-not-leak\nlast verifier line\n")
    return trial


def test_harbor_rollout_distinguishes_task_agent_and_infra_failures(tmp_path: Path) -> None:
    module = _harbor_rollout_module()
    jobs = tmp_path / "jobs"
    _write_trial(jobs, name="task-failed", reward=0)
    _write_trial(jobs, name="task-partial", reward=0.5)
    _write_trial(jobs, name="task-passed", reward=1)
    _write_trial(
        jobs,
        name="verifier-timeout",
        reward=None,
        exception_type="VerifierTimeoutError",
        exception_message="Verifier execution timed out after 120 seconds",
    )
    _write_trial(
        jobs,
        name="agent-timeout",
        reward=None,
        exception_type="AgentTimeoutError",
        exception_message="Agent execution timed out",
    )

    cases = module._collect_cases(jobs)
    by_name = {case["trial_name"]: case for case in cases}

    assert by_name["task-failed"]["outcome"] == "failed"
    assert by_name["task-partial"]["outcome"] == "failed"
    assert by_name["task-passed"]["outcome"] == "passed"
    assert by_name["verifier-timeout"]["outcome"] == "infra_error"
    assert by_name["agent-timeout"]["outcome"] == "agent_error"
    assert by_name["task-failed"]["instruction"] == "Fix task task-failed."
    assert by_name["task-failed"]["tool_calls"][0]["name"] == "exec"
    assert "missing output" in by_name["task-failed"]["observations"][0]
    assert "must-not-leak" not in by_name["task-failed"]["verifier_output"]
    assert "[REDACTED]" in by_name["task-failed"]["verifier_output"]
    assert "json-secret" not in module._redact('{"OPENAI_API_KEY":"json-secret"}')

    feedback = module._render_feedback(cases, 30000)
    assert "Actionable task failures" in feedback
    assert "Infrastructure-only errors" in feedback
    assert "do not mutate the agent solely" in feedback


def test_feedback_bundle_exposes_current_rollout_to_mutator(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run_dir = workspace / "runs" / "gen-1"
    (run_dir / "rollout").mkdir(parents=True)
    (run_dir / "rollout" / "feedback.md").write_text("# Harbor Rollout Feedback\n\nfailed task evidence\n")

    manifest = write_feedback_bundle(workspace=workspace, run_dir=run_dir)

    copied = run_dir / "feedback" / "failures" / "rollout.md"
    assert copied.read_text().endswith("failed task evidence\n")
    assert "[current rollout](failures/rollout.md)" in (run_dir / "feedback" / "index.md").read_text()
    assert "feedback/failures/rollout.md" in manifest
