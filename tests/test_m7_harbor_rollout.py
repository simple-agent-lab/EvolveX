import importlib.util
import json
from pathlib import Path

from conftest import init_workspace

from evolve.feedback import write_feedback_bundle
from evolve.trace_analysis import VARIANTS, write_evidence_bundle

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
    (trial / "verifier" / "test-stdout.txt").write_text(
        "OPENAI_API_KEY=must-not-leak\nmissing required artifact output\n"
    )
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
    assert by_name["task-failed"]["events"][-1]["source"] == "agent"
    assert by_name["task-failed"]["artifact_inventory"]["agent"] == ["trajectory.json"]
    assert "must-not-leak" not in by_name["task-failed"]["verifier_output"]
    assert "[REDACTED]" in by_name["task-failed"]["verifier_output"]
    assert "json-secret" not in module._redact('{"OPENAI_API_KEY":"json-secret"}')


def test_harbor_rollout_reads_codex_session_jsonl_when_trajectory_is_absent(tmp_path: Path) -> None:
    module = _harbor_rollout_module()
    jobs = tmp_path / "jobs"
    trial = _write_trial(jobs, name="codex-session", reward=0)
    (trial / "agent" / "trajectory.json").unlink()
    session = trial / "agent" / "sessions" / "2026" / "session.jsonl"
    session.parent.mkdir(parents=True)
    rows = [
        {"timestamp": "t1", "type": "event_msg", "payload": {"type": "user_message", "message": "Fix it."}},
        {"timestamp": "t2", "type": "event_msg", "payload": {"type": "agent_message", "message": "Inspecting."}},
        {
            "timestamp": "t3",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": '{"cmd":"pytest"}',
                "call_id": "c1",
            },
        },
        {
            "timestamp": "t4",
            "type": "response_item",
            "payload": {"type": "function_call_output", "output": "1 failed", "call_id": "c1"},
        },
        {"timestamp": "t5", "type": "event_msg", "payload": {"type": "agent_message", "message": "Done."}},
    ]
    session.write_text("".join(json.dumps(row) + "\n" for row in rows))

    case = module._collect_cases(jobs)[0]

    assert case["instruction"] == "Fix it."
    assert case["agent_messages"] == ["Inspecting.", "Done."]
    assert case["tool_calls"] == [{"name": "exec_command", "arguments": '{"cmd":"pytest"}'}]
    assert case["observations"] == ["1 failed"]
    assert [event["type"] for event in case["events"]] == [
        "message",
        "message",
        "tool_call",
        "tool_result",
        "message",
    ]


def test_harbor_rollout_bounds_codex_session_events_to_the_latest_trace_window(tmp_path: Path) -> None:
    module = _harbor_rollout_module()
    jobs = tmp_path / "jobs"
    trial = _write_trial(jobs, name="long-codex-session", reward=0)
    (trial / "agent" / "trajectory.json").unlink()
    session = trial / "agent" / "sessions" / "session.jsonl"
    session.parent.mkdir(parents=True)
    rows = [
        {
            "timestamp": f"t{index}",
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": f"message-{index}"},
        }
        for index in range(100)
    ]
    session.write_text("".join(json.dumps(row) + "\n" for row in rows))

    case = module._collect_cases(jobs)[0]

    assert len(case["events"]) == 32
    assert case["events"][0]["message"] == "message-68"
    assert case["events"][-1]["message"] == "message-99"


def test_feedback_bundle_exposes_current_rollout_to_mutator(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run_dir = workspace / "runs" / "gen-1"
    (run_dir / "trace_analyzer").mkdir(parents=True)
    (run_dir / "trace_analyzer" / "feedback.md").write_text("# Trace Analysis Feedback\n\nfailed task evidence\n")

    manifest = write_feedback_bundle(workspace=workspace, run_dir=run_dir)

    copied = run_dir / "feedback" / "failures" / "trace_analyzer.md"
    assert copied.read_text().endswith("failed task evidence\n")
    assert "[current trace analysis](failures/trace_analyzer.md)" in (run_dir / "feedback" / "index.md").read_text()
    assert "feedback/failures/trace_analyzer.md" in manifest


def test_trace_analyzer_variants_share_raw_harbor_facts(tmp_path: Path) -> None:
    module = _harbor_rollout_module()
    jobs = tmp_path / "jobs"
    _write_trial(jobs, name="missing-output-a", reward=0)
    _write_trial(jobs, name="missing-output-b", reward=0)
    _write_trial(jobs, name="passing", reward=1)
    cases = module._collect_cases(jobs)

    for variant in VARIANTS:
        run_dir = tmp_path / variant
        selected, artifacts = write_evidence_bundle(
            run_dir,
            cases,
            variant=variant,
            max_chars=100_000,
        )
        assert f"Variant: {variant}" in selected
        assert "trace_analyzer/evidence/raw_traces.jsonl" in artifacts
        assert (run_dir / "trace_analyzer" / "evidence" / "manifest.json").is_file()

    patterns = json.loads(
        (tmp_path / "failure_patterns" / "trace_analyzer" / "evidence" / "failure_patterns.json").read_text()
    )
    assert patterns[0]["support"] == 2
    assert patterns[0]["signature"]["terminal_cause"] == "missing_artifact"
    passing = json.loads(
        (tmp_path / "failure_patterns" / "trace_analyzer" / "evidence" / "passing_behaviors.json").read_text()
    )
    assert passing[0]["task_name"] == "harbor/passing"


def test_feedback_bundle_copies_selected_evidence_and_history(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run_dir = workspace / "runs" / "gen-1"
    evidence = run_dir / "trace_analyzer" / "evidence"
    evidence.mkdir(parents=True)
    (run_dir / "trace_analyzer" / "feedback.md").write_text("duplicate selected view\n")
    (evidence / "selected.md").write_text("# selected profile evidence\n")
    (evidence / "manifest.json").write_text(json.dumps({"selected_variant": "failure_patterns"}))
    (evidence / "metrics.json").write_text(json.dumps({"trials": 1}))

    manifest = write_feedback_bundle(workspace=workspace, run_dir=run_dir)

    assert (run_dir / "feedback" / "evidence" / "selected.md").read_text().startswith("# selected")
    assert "feedback/evidence/history.json" in manifest
    index = (run_dir / "feedback" / "index.md").read_text()
    assert "[selected trace evidence](evidence/selected.md)" in index
    assert "[current trace analysis]" not in index
