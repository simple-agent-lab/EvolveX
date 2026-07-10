"""Run the current checkout through Harbor and distill mutation feedback."""

# ruff: noqa: E402

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, RolloutOperator, RolloutResult

_INFRA_EXCEPTION_MARKERS = (
    "verifier",
    "environment",
    "docker",
    "build",
    "download",
    "network",
)
_WRAPPER_MARKERS = ("<environment_context>", "<recommended_plugins>", "<permissions instructions>")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b([a-z0-9_-]*(?:api[_-]?key|access[_-]?token|auth(?:orization)?|secret|password))\b"
    r"([\"']?)(\s*[:=]\s*)([^\s,;}]+)"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _redact(text: str) -> str:
    text = _BEARER.sub("Bearer [REDACTED]", text)
    return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED]", text)


def _clip(value: object, limit: int, *, tail: bool = False) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, sort_keys=True)
        except (TypeError, ValueError):
            text = str(value)
    text = _redact(text.strip())
    if len(text) <= limit:
        return text
    marker = f"\n...[truncated {len(text) - limit} chars]...\n"
    kept = max(1, limit - len(marker))
    return marker + text[-kept:] if tail else text[:kept] + marker


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_text(path: Path, limit: int, *, tail: bool = False) -> str:
    try:
        return _clip(path.read_text(errors="replace"), limit, tail=tail)
    except OSError:
        return ""


def _load_eval_env(checkout: Path) -> dict[str, str]:
    path = checkout / "evaluator" / "eval.env"
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw = stripped.split("=", 1)
        try:
            parts = shlex.split(raw, posix=True)
            value = " ".join(parts) if parts else ""
        except ValueError:
            value = raw.strip().strip("\"'")
        values[key.strip()] = os.path.expanduser(os.path.expandvars(value))
    return values


def _reward(payload: dict[str, Any], trial_dir: Path) -> float | None:
    verifier = payload.get("verifier_result")
    rewards = verifier.get("rewards") if isinstance(verifier, dict) else None
    reward = rewards.get("reward") if isinstance(rewards, dict) else None
    if isinstance(reward, (int, float)) and not isinstance(reward, bool):
        return float(reward)
    reward_path = trial_dir / "verifier" / "reward.txt"
    try:
        return float(reward_path.read_text().strip()) if reward_path.exists() else None
    except (OSError, ValueError):
        return None


def _outcome(reward: float | None, exception_type: str, pass_threshold: float) -> str:
    if reward is not None:
        return "passed" if reward >= pass_threshold else "failed"
    lowered = exception_type.lower()
    if any(marker in lowered for marker in _INFRA_EXCEPTION_MARKERS):
        return "infra_error"
    if exception_type:
        return "agent_error"
    return "incomplete"


def _duration_seconds(value: object) -> float | None:
    if not isinstance(value, dict):
        return None
    try:
        start = datetime.fromisoformat(str(value["started_at"]).replace("Z", "+00:00"))
        finish = datetime.fromisoformat(str(value["finished_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return None
    return round((finish - start).total_seconds(), 3)


def _trajectory_details(trial_dir: Path, field_limit: int) -> dict[str, Any]:
    trajectory = _read_json(trial_dir / "agent" / "trajectory.json")
    steps = trajectory.get("steps")
    if not isinstance(steps, list):
        steps = []

    instructions: list[str] = []
    messages: list[str] = []
    tool_calls: list[dict[str, str]] = []
    observations: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        source = step.get("source")
        message = step.get("message")
        if source == "user" and isinstance(message, str) and not any(marker in message for marker in _WRAPPER_MARKERS):
            instructions.append(_clip(message, field_limit))
        if source != "agent":
            continue
        if isinstance(message, str) and message.strip():
            messages.append(_clip(message, field_limit))
        calls = step.get("tool_calls")
        if isinstance(calls, list):
            for call in calls:
                if not isinstance(call, dict):
                    continue
                tool_calls.append(
                    {
                        "name": str(call.get("function_name") or call.get("name") or "unknown"),
                        "arguments": _clip(call.get("arguments") or {}, field_limit),
                    }
                )
        observation = step.get("observation")
        results = observation.get("results") if isinstance(observation, dict) else None
        if isinstance(results, list):
            for result in results:
                if isinstance(result, dict) and result.get("content"):
                    observations.append(_clip(result["content"], field_limit, tail=True))

    raw_agent_output = ""
    if not messages and not tool_calls:
        candidates = sorted((trial_dir / "agent").glob("*.txt")) if (trial_dir / "agent").exists() else []
        raw_agent_output = "\n".join(_read_text(path, field_limit, tail=True) for path in candidates[:2])
    return {
        "instruction": instructions[-1] if instructions else "",
        "agent_messages": messages[-4:],
        "tool_calls": tool_calls[-8:],
        "observations": observations[-8:],
        "raw_agent_output": raw_agent_output,
    }


def _verifier_output(trial_dir: Path, field_limit: int) -> str:
    verifier_dir = trial_dir / "verifier"
    if not verifier_dir.exists():
        return ""
    parts: list[str] = []
    for path in sorted(verifier_dir.rglob("*")):
        if not path.is_file() or path.name in {"reward.txt", "reward.json"}:
            continue
        text = _read_text(path, field_limit, tail=True)
        if text:
            parts.append(f"[{path.relative_to(verifier_dir).as_posix()}]\n{text}")
    return _clip("\n\n".join(parts), field_limit * 2, tail=True)


def _collect_cases(jobs_dir: Path, field_limit: int = 2000, pass_threshold: float = 1.0) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    if not jobs_dir.exists():
        return cases
    for result_path in sorted(jobs_dir.rglob("result.json")):
        payload = _read_json(result_path)
        if not payload.get("trial_name") or not payload.get("task_name"):
            continue
        trial_dir = result_path.parent
        exception = payload.get("exception_info")
        exception = exception if isinstance(exception, dict) else {}
        exception_type = str(exception.get("exception_type") or "")
        reward = _reward(payload, trial_dir)
        agent_result = payload.get("agent_result")
        agent_result = agent_result if isinstance(agent_result, dict) else {}
        details = _trajectory_details(trial_dir, field_limit)
        cases.append(
            {
                "trial_name": str(payload.get("trial_name")),
                "task_name": str(payload.get("task_name")),
                "reward": reward,
                "outcome": _outcome(reward, exception_type, pass_threshold),
                "instruction": details["instruction"],
                "agent_messages": details["agent_messages"],
                "tool_calls": details["tool_calls"],
                "observations": details["observations"],
                "raw_agent_output": details["raw_agent_output"],
                "verifier_output": _verifier_output(trial_dir, field_limit),
                "exception": {
                    "type": exception_type,
                    "message": _clip(exception.get("exception_message") or "", field_limit),
                },
                "usage": {
                    "input_tokens": agent_result.get("n_input_tokens"),
                    "cache_tokens": agent_result.get("n_cache_tokens"),
                    "output_tokens": agent_result.get("n_output_tokens"),
                    "cost_usd": agent_result.get("cost_usd"),
                },
                "timing_s": {
                    name: _duration_seconds(payload.get(name))
                    for name in ("environment_setup", "agent_setup", "agent_execution", "verifier")
                },
                "result_path": str(result_path),
            }
        )
    return cases


def _case_markdown(case: dict[str, Any], *, concise: bool = False) -> str:
    lines = [
        f"### {case['task_name']}",
        f"- Outcome: {case['outcome']}",
        f"- Reward: {case['reward']}",
    ]
    usage = case.get("usage") or {}
    lines.append(
        "- Usage: input=%s cache=%s output=%s cost_usd=%s"
        % (usage.get("input_tokens"), usage.get("cache_tokens"), usage.get("output_tokens"), usage.get("cost_usd"))
    )
    if concise:
        if case.get("instruction"):
            lines.append(f"- Instruction: {case['instruction']}")
        if case.get("agent_messages"):
            lines.append(f"- Final response: {case['agent_messages'][-1]}")
        return "\n".join(lines)
    sections = (
        ("Task instruction", case.get("instruction")),
        ("Agent messages", "\n".join(f"- {item}" for item in case.get("agent_messages") or [])),
        (
            "Tool calls",
            "\n".join(f"- `{call['name']}`: {call['arguments']}" for call in case.get("tool_calls") or []),
        ),
        ("Tool observations", "\n".join(f"- {item}" for item in case.get("observations") or [])),
        ("Raw agent output", case.get("raw_agent_output")),
        ("Verifier output", case.get("verifier_output")),
    )
    for title, content in sections:
        if content:
            lines.extend(["", f"#### {title}", str(content)])
    exception = case.get("exception") or {}
    if exception.get("type") or exception.get("message"):
        lines.extend(["", "#### Exception", f"{exception.get('type')}: {exception.get('message')}"])
    return "\n".join(lines)


def _render_feedback(cases: list[dict[str, Any]], max_chars: int) -> str:
    counts = {name: sum(case["outcome"] == name for case in cases) for name in _OUTCOME_ORDER}
    rewards = [case["reward"] for case in cases if isinstance(case.get("reward"), (int, float))]
    parts = [
        "# Harbor Rollout Feedback",
        "",
        "Use task failures and agent execution errors as mutation evidence. Infrastructure errors are diagnostic only; do not mutate the agent solely to address them.",
        "",
        "- Trials: %s" % len(cases),
        "- Passed: %s" % counts["passed"],
        "- Failed: %s" % counts["failed"],
        "- Agent errors: %s" % counts["agent_error"],
        "- Infrastructure errors: %s" % (counts["infra_error"] + counts["incomplete"]),
        "- Mean observed reward: %s" % (round(sum(rewards) / len(rewards), 6) if rewards else "unavailable"),
    ]
    headings = {
        "failed": "Actionable task failures",
        "agent_error": "Agent execution errors",
        "infra_error": "Infrastructure-only errors",
        "incomplete": "Incomplete trials",
        "passed": "Successful samples",
    }
    for outcome in _OUTCOME_ORDER:
        selected = [case for case in cases if case["outcome"] == outcome]
        if not selected:
            continue
        parts.extend(["", f"## {headings[outcome]}", ""])
        parts.extend(_case_markdown(case, concise=outcome == "passed") for case in selected)
    return _clip("\n\n".join(parts) + "\n", max_chars)


_OUTCOME_ORDER = ("failed", "agent_error", "infra_error", "incomplete", "passed")


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def _float_value(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _run_timeout() -> float | None:
    try:
        outer = float(os.environ.get("EVOLVE_OPERATOR_TIMEOUT_S", ""))
    except ValueError:
        return None
    return max(0.1, outer - min(5.0, max(0.5, outer * 0.05)))


def _run_harbor(command: list[str], checkout: Path, log_path: Path) -> int:
    env = {
        **os.environ,
        "PYTHONPATH": str(checkout) + (f":{os.environ['PYTHONPATH']}" if os.environ.get("PYTHONPATH") else ""),
    }
    start = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=checkout,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=_run_timeout())
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()
        output, _ = process.communicate()
        output = (output or "") + "\nharbor rollout timed out\n"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(_redact(f"wall_s={time.monotonic() - start:.3f}\n{output or ''}"))
    return process.returncode if process.returncode is not None else 1


class HarborRollout(RolloutOperator):
    def rollout(self, checkout: Path, ctx: OperatorContext) -> RolloutResult:
        harbor = shutil.which("harbor")
        if harbor is None:
            raise SystemExit("harbor rollout requires the harbor CLI on PATH")
        eval_env = _load_eval_env(checkout)
        tasks = str(ctx.config.get("path") or os.environ.get("EVOLVE_HARBOR_ROLLOUT_TASKS") or "")
        agent = str(ctx.config.get("agent") or eval_env.get("EVOLVE_HARBOR_AGENT") or "")
        if not tasks:
            raise SystemExit(
                "harbor rollout requires an explicit train task path via operators.rollout.path "
                "or EVOLVE_HARBOR_ROLLOUT_TASKS; do not use gate or sealed evaluator tasks"
            )
        if not agent:
            raise SystemExit("harbor rollout requires an agent in config or evaluator/eval.env")

        budget_tasks = _positive_int(ctx.config.get("budget_tasks"), 8)
        default_concurrent = _positive_int(eval_env.get("EVOLVE_HARBOR_N_CONCURRENT"), budget_tasks)
        n_concurrent = min(budget_tasks, _positive_int(ctx.config.get("n_concurrent"), default_concurrent))
        field_limit = _positive_int(ctx.config.get("field_limit"), 2000)
        max_feedback_chars = _positive_int(ctx.config.get("max_feedback_chars"), 30000)
        pass_threshold = _float_value(ctx.config.get("pass_threshold"), 1.0)
        jobs_root = Path(
            str(
                ctx.config.get("jobs_dir")
                or os.environ.get("EVOLVE_ROLLOUT_JOBS_DIR")
                or Path.home() / ".evolve" / "harbor-rollouts" / ctx.workspace.name
            )
        ).expanduser()
        jobs_dir = jobs_root / f"gen-{ctx.genid}"
        if jobs_dir.exists():
            shutil.rmtree(jobs_dir)
        jobs_dir.mkdir(parents=True, exist_ok=True)

        command = [
            harbor,
            "run",
            "-p",
            tasks,
            "--agent",
            agent,
            "--jobs-dir",
            str(jobs_dir),
            "--n-attempts",
            "1",
            "-n",
            str(n_concurrent),
            "--n-tasks",
            str(budget_tasks),
            "-y",
            "-q",
        ]
        model = ctx.config.get("model") or os.environ.get("EVOLVE_HARBOR_MODEL")
        if model:
            command.extend(["--model", str(model)])
        include_task = ctx.config.get("include_task_name")
        if include_task:
            command.extend(["--include-task-name", str(include_task)])

        rollout_dir = ctx.run_dir / "rollout"
        returncode = _run_harbor(command, checkout, rollout_dir / "harbor.log")
        cases = _collect_cases(jobs_dir, field_limit=field_limit, pass_threshold=pass_threshold)
        _write_json(rollout_dir / "cases.json", cases)
        feedback = _render_feedback(cases, max_feedback_chars)
        (rollout_dir / "feedback.md").write_text(feedback)
        if not cases:
            raise SystemExit(
                f"harbor rollout produced no trial results (exit {returncode}); see {rollout_dir / 'harbor.log'}"
            )

        rewards = [case["reward"] for case in cases if isinstance(case.get("reward"), (int, float))]
        counts = {name: sum(case["outcome"] == name for case in cases) for name in _OUTCOME_ORDER}
        summary = {
            "variant": "harbor",
            "harbor_returncode": returncode,
            "tasks_requested": budget_tasks,
            "tasks_observed": len(cases),
            "passed": counts["passed"],
            "failed": counts["failed"],
            "agent_errors": counts["agent_error"],
            "infra_errors": counts["infra_error"] + counts["incomplete"],
            "mean_observed_reward": round(sum(rewards) / len(rewards), 6) if rewards else None,
            "jobs_dir": str(jobs_dir),
        }
        return RolloutResult(
            summary=summary,
            artifacts=[
                "rollout/harbor.log",
                "rollout/cases.json",
                "rollout/feedback.md",
                f"harbor-jobs:{jobs_dir}",
            ],
        )


if __name__ == "__main__":
    sdk.main(HarborRollout)
