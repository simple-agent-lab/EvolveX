import importlib.util
import json
import random
import sys
from pathlib import Path

import pytest

from evolve.agent import AgentCommandError, AgentRunResult
from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "library" / "trace_analyzer" / "ahe.py"
    spec = importlib.util.spec_from_file_location("ahe_trace_analyzer_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ctx(tmp_path: Path, *, genid: str = "1", parent: str = "0") -> OperatorContext:
    workspace = tmp_path / "workspace"
    checkout = workspace / "checkout"
    run_dir = workspace / "runs" / f"gen-{genid}"
    checkout.mkdir(parents=True, exist_ok=True)
    (checkout / "evolve.yaml").write_text(
        "operators:\n"
        "  meta_agent:\n"
        "    variant: ahe\n"
        "    runner: harbor\n"
        "    agent: mini-swe-agent\n"
        "    model: gpt-test\n"
        "    environment: docker\n"
        "    editable_roots: [target]\n"
    )
    return OperatorContext(
        workspace=workspace,
        checkout=checkout,
        run_dir=run_dir,
        genid=genid,
        parent=parent,
        round=None,
        fan_out=1,
        config={
            "field_limit": 120,
            "max_tasks": 90,
            "max_concurrent": 2,
            "timeout_per_task": 30,
            "retry_attempts": 3,
        },
        rng=random.Random(0),
    )


def _case(name: str, outcome: str, reward: float | None, *, task: str | None = None) -> dict:
    return {
        "trial_name": name,
        "task_name": task or name,
        "outcome": outcome,
        "reward": reward,
        "instruction": f"Fix {name}",
        "agent_messages": [f"inspect {name}", f"finish {name}"],
        "tool_calls": [{"name": "exec", "arguments": f"pytest {name}"}],
        "observations": [f"result for {name}"],
        "events": [{"index": 0, "type": "message", "message": f"inspect {name}"}],
        "verifier_output": f"verifier says {outcome}",
        "verifier_rewards": {"reward": reward},
        "exception": {},
        "usage": {"input_tokens": 10, "cost_usd": 0.01},
        "timing_s": {"agent_execution": 1.5},
    }


def _write_cases(run_dir: Path, cases: list[dict]) -> None:
    rollout = run_dir / "rollout"
    rollout.mkdir(parents=True, exist_ok=True)
    (rollout / "cases.json").write_text(json.dumps(cases))


def _fake_debugger(checkout, prompt, ctx, *, output_dir, job_name, timeout_s):
    del checkout, ctx, output_dir, job_name, timeout_s
    response = "ROOT CAUSE: retry policy" if "ROOT CAUSE:" in prompt else "KEY STRATEGY: inspect first"
    return AgentRunResult(response, "", response, 0, 0.1, {"usd": 0.25})


def test_ahe_groups_all_rollouts_per_task_and_prioritizes_failures() -> None:
    module = _module()
    cases = [
        _case("pass-a-1", "passed", 1.0, task="task-a"),
        _case("pass-a-2", "passed", 1.0, task="task-a"),
        _case("fail-b-1", "failed", 0.0, task="task-b"),
        _case("pass-b-2", "passed", 1.0, task="task-b"),
    ]

    jobs = module._build_jobs(cases, max_tasks=90)

    assert [job.task_name for job in jobs] == ["task-b", "task-a"]
    assert [case["trial_name"] for case in jobs[0].cases] == ["fail-b-1", "pass-b-2"]
    assert jobs[0].mode == "debug"
    assert jobs[1].mode == "summary"
    assert "PASS vs FAIL" in module._debugger_prompt(jobs[0])
    assert "REUSABLE PATTERN" in module._debugger_prompt(jobs[1])
    assert [job.task_name for job in module._build_jobs(cases, max_tasks=1)] == ["task-b"]


def test_ahe_debugger_reuses_only_allowlisted_meta_agent_config(tmp_path: Path) -> None:
    module = _module()
    ctx = _ctx(tmp_path)
    config = module._debugger_runner_config(ctx.checkout)

    assert config == {
        "agent": "mini-swe-agent",
        "model": "gpt-test",
        "environment": "docker",
        "max_retries": 0,
    }
    assert "editable_roots" not in config
    assert "runner" not in config


def test_ahe_miniswe_debugger_prompt_includes_submission_protocol() -> None:
    module = _module()
    job = module._build_jobs([_case("task-a", "failed", 0)], 90)[0]

    prompt = module._debugger_runner_prompt(job, {"agent": "mini-swe-agent"})

    assert "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" in prompt
    assert "standalone Bash tool call" in prompt
    assert "A response containing only the Bash call is invalid" in prompt
    assert module._debugger_runner_prompt(job, {"agent": "codex"}) == module._debugger_prompt(job)


def test_ahe_debugger_retries_and_fails_visibly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    ctx = _ctx(tmp_path)
    job = module._build_jobs([_case("task-a", "failed", 0)], 90)[0]
    attempts = 0

    def flaky(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise AgentCommandError("temporary", returncode=1)
        return _fake_debugger(*args, **kwargs)

    monkeypatch.setattr(module, "run_readonly_agent", flaky)
    assert module._run_debugger_job(ctx.checkout, ctx, job).response.startswith("ROOT CAUSE")
    assert attempts == 3

    monkeypatch.setattr(
        module,
        "run_readonly_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(AgentCommandError("failed", returncode=1)),
    )
    with pytest.raises(AgentCommandError, match="failed"):
        module._run_debugger_job(ctx.checkout, ctx, job)


def test_ahe_analyzer_writes_official_reports_and_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    ctx = _ctx(tmp_path)
    _write_cases(
        ctx.run_dir,
        [_case("fail-1", "failed", 0, task="task-a"), _case("pass-1", "passed", 1, task="task-b")],
    )
    monkeypatch.setattr(module, "run_readonly_agent", _fake_debugger)

    result = module.AheTraceAnalyzer().analyze(ctx.checkout, ctx)

    analysis = ctx.run_dir / "trace_analyzer" / "analysis"
    assert "ROOT CAUSE" in (analysis / "detail" / "task-a.md").read_text()
    assert "task-a" in (analysis / "overview.md").read_text()
    change = json.loads((analysis / "change_evaluation.json").read_text())
    assert change["status"] == "baseline"
    assert result.summary["tasks"] == 2
    assert result.summary["debugger_usd"] == 0.5
    assert "trace_analyzer/analysis/detail/task-a.md" in result.artifacts


def test_ahe_analyzer_attributes_prior_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    ctx = _ctx(tmp_path, genid="2", parent="1")
    prior = ctx.workspace / "runs" / "gen-1"
    _write_cases(
        prior,
        [_case("old-a", "failed", 0, task="task-a"), _case("old-b", "passed", 1, task="task-b")],
    )
    manifest_dir = prior / "meta_agent"
    manifest_dir.mkdir()
    (manifest_dir / "change_manifest.json").write_text(
        json.dumps(
            {
                "changes": [
                    {"predicted_fixes": ["task-a"], "risk_tasks": ["task-b"]},
                ]
            }
        )
    )
    _write_cases(
        ctx.run_dir,
        [_case("new-a", "passed", 1, task="task-a"), _case("new-b", "failed", 0, task="task-b")],
    )
    monkeypatch.setattr(module, "run_readonly_agent", _fake_debugger)

    module.AheTraceAnalyzer().analyze(ctx.checkout, ctx)

    change = json.loads((ctx.run_dir / "trace_analyzer" / "analysis" / "change_evaluation.json").read_text())
    assert change["transitions"] == {"task-a": "fail_to_pass", "task-b": "pass_to_fail"}
    assert change["prediction_results"]["task-a"] == "confirmed"
    assert change["risk_results"]["task-b"] == "realized"


def test_ahe_bounds_and_redacts_case_fields() -> None:
    module = _module()
    secret = "OPENAI_API_KEY=must-not-leak " + "x" * 200
    normalized = module._normalize(
        _case("secret", "failed", 0)
        | {
            "instruction": secret,
            "agent_messages": [secret] * 100,
            "usage": {"password": "bare-secret-value"},
        },
        40,
    )
    rendered = json.dumps(normalized)
    assert "must-not-leak" not in rendered
    assert "bare-secret-value" not in rendered
    assert "[REDACTED]" in rendered
    assert module.TRUNCATION_KEY in rendered


def test_ahe_missing_cases_fails_instead_of_falling_back(tmp_path: Path) -> None:
    module = _module()
    ctx = _ctx(tmp_path)
    with pytest.raises(RuntimeError, match="missing rollout cases"):
        module.AheTraceAnalyzer().analyze(ctx.checkout, ctx)
