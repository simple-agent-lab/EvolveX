import importlib.util
import json
import random
from pathlib import Path

import pytest

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "library" / "trace_analyzer" / "ahe.py"
    spec = importlib.util.spec_from_file_location("ahe_trace_analyzer_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ctx(tmp_path: Path, *, max_cases: int = 3, field_limit: int = 80) -> OperatorContext:
    workspace = tmp_path / "workspace"
    checkout = workspace / "checkout"
    run_dir = workspace / "runs" / "gen-1"
    checkout.mkdir(parents=True)
    return OperatorContext(
        workspace=workspace,
        checkout=checkout,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={"max_cases": max_cases, "field_limit": field_limit},
        rng=random.Random(0),
    )


def _case(name: str, outcome: str, reward: float | None) -> dict:
    return {
        "trial_name": name,
        "task_name": f"task/{name}",
        "outcome": outcome,
        "reward": reward,
        "instruction": f"Fix {name}",
        "agent_messages": [f"inspect {name}", f"finish {name}"],
        "tool_calls": [{"name": "exec", "arguments": f"pytest {name}"}],
        "observations": [f"result for {name}"],
        "events": [{"index": 0, "type": "message", "message": f"inspect {name}"}],
        "verifier_output": f"verifier says {outcome}",
        "verifier_rewards": {"reward": reward},
        "exception": {"type": "", "message": ""},
        "usage": {"input_tokens": 10, "cost_usd": 0.01},
        "timing_s": {"agent_execution": 1.5},
    }


def _write_cases(ctx: OperatorContext, cases: list[dict]) -> None:
    rollout = ctx.run_dir / "rollout"
    rollout.mkdir(parents=True)
    (rollout / "cases.json").write_text(json.dumps(cases))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)


def test_ahe_analyzer_selects_failures_first_in_rollout_order_and_writes_exact_artifacts(tmp_path: Path) -> None:
    module = _module()
    ctx = _ctx(tmp_path)
    _write_cases(
        ctx,
        [
            _case("pass-1", "passed", 1),
            _case("fail-1", "failed", 0),
            _case("pass-2", "passed", 1),
            _case("fail-2", "failed", 0),
        ],
    )

    result = module.AheTraceAnalyzer().analyze(ctx.checkout, ctx)

    evidence = ctx.run_dir / "trace_analyzer" / "evidence"
    cases = _jsonl(evidence / "cases.jsonl")
    assert [row["trial_name"] for row in cases] == ["fail-1", "fail-2", "pass-1"]
    assert [row["outcome"] for row in cases] == ["failed", "failed", "passed"]
    assert result.summary == {
        "status": "ok",
        "error": None,
        "observed": 4,
        "selected": 3,
        "outcomes": {"failed": 2, "passed": 2},
        "mean_reward": 0.5,
    }
    assert result.artifacts == [
        "trace_analyzer/feedback.md",
        "trace_analyzer/evidence/selected.md",
        "trace_analyzer/evidence/overview.json",
        "trace_analyzer/evidence/cases.jsonl",
    ]
    assert (ctx.run_dir / "trace_analyzer" / "feedback.md").read_text() == (evidence / "selected.md").read_text()
    overview = json.loads((evidence / "overview.json").read_text())
    assert [row["trial_name"] for row in overview["cases"]] == ["fail-1", "fail-2", "pass-1"]


def test_ahe_analyzer_bounds_and_redacts_malformed_case_fields(tmp_path: Path) -> None:
    module = _module()
    field_limit = 24
    ctx = _ctx(tmp_path, max_cases=2, field_limit=field_limit)
    long_secret = "OPENAI_API_KEY=must-not-leak " + "x" * 100
    wide = [{"message": long_secret, "nested": [[long_secret] * 50] * 10} for _ in range(100)]
    _write_cases(
        ctx,
        [
            {
                "trial_name": "malformed",
                "task_name": "task/malformed",
                "outcome": "failed",
                "reward": 0,
                "instruction": long_secret,
                "agent_messages": [long_secret] * 100,
                "tool_calls": [{"name": "exec", "arguments": "Bearer top-secret-token"}] * 100,
                "observations": [long_secret] * 100,
                "events": wide,
                "verifier_output": long_secret,
                "verifier_rewards": {f"secret-{index}": long_secret for index in range(100)},
                "exception": {"type": "Error", "message": long_secret},
                "usage": {"password": "bare-secret-value"},
            },
            {
                "trial_name": "sparse",
                "outcome": "passed",
                "agent_messages": "not-a-list",
                "tool_calls": "not-a-list",
                "observations": None,
                "events": "not-a-list",
                "exception": "not-a-dict",
                "usage": [],
            },
        ],
    )

    module.AheTraceAnalyzer().analyze(ctx.checkout, ctx)

    rows = _jsonl(ctx.run_dir / "trace_analyzer" / "evidence" / "cases.jsonl")
    rendered = json.dumps(rows, sort_keys=True)
    assert "must-not-leak" not in rendered
    assert "top-secret-token" not in rendered
    assert "bare-secret-value" not in rendered
    assert "[REDACTED]" in rendered
    clipped_fields = list(_strings(rows))
    assert all(len(value) <= field_limit + 64 for value in clipped_fields)
    assert len(rows[0]["agent_messages"]) <= 33
    assert len(rows[0]["tool_calls"]) <= 33
    assert len(rows[0]["events"]) <= 33
    assert "__ahe_truncated__" in rendered
    assert rows[1]["agent_messages"] == []
    assert rows[1]["tool_calls"] == []
    assert rows[1]["observations"] == []
    assert rows[1]["events"] == []
    assert rows[1]["exception"] == {}
    assert rows[1]["usage"] == {}


@pytest.mark.parametrize("payload", [None, "not-json", "{}"])
def test_ahe_analyzer_emits_exact_error_artifacts_when_current_cases_are_unavailable(
    tmp_path: Path, payload: str | None
) -> None:
    module = _module()
    ctx = _ctx(tmp_path)
    rollout = ctx.run_dir / "rollout"
    rollout.mkdir(parents=True)
    if payload is not None:
        (rollout / "cases.json").write_text(payload)

    result = module.AheTraceAnalyzer().analyze(ctx.checkout, ctx)

    assert result.summary["status"] == "error"
    assert result.summary["observed"] == 0
    assert result.summary["selected"] == 0
    assert result.artifacts == [
        "trace_analyzer/feedback.md",
        "trace_analyzer/evidence/selected.md",
        "trace_analyzer/evidence/overview.json",
        "trace_analyzer/evidence/cases.jsonl",
    ]
    for artifact in result.artifacts:
        assert (ctx.run_dir / artifact).is_file()
    assert _jsonl(ctx.run_dir / "trace_analyzer" / "evidence" / "cases.jsonl") == []


def test_ahe_analyzer_reads_only_current_rollout_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    ctx = _ctx(tmp_path)
    _write_cases(ctx, [_case("current", "failed", 0)])
    cases_path = ctx.run_dir / "rollout" / "cases.json"
    original = Path.read_text
    reads: list[Path] = []

    def guarded_read(path: Path, *args, **kwargs):
        reads.append(path)
        if path != cases_path:
            raise AssertionError(f"unexpected read: {path}")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)

    module.AheTraceAnalyzer().analyze(ctx.checkout, ctx)

    assert reads == [cases_path]
