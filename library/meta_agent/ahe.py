"""AHE strategy: turn current evidence into one testable harness change."""

# ruff: noqa: E402

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

from evolve.agent import AgentCommandError
from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult, OperatorContext
from evolve.patching import create_candidate_patch, load_surface_policy, patch_parent_ref
from library.meta_agent.runners import run_agent, runner_name
from library.meta_agent.support.evidence import load_feedback

AHE_PROMPT = """# Agentic Harness Engineering

Improve the MiniSWE harness under `target/`; do not solve a benchmark task
directly. Treat current trace evidence as observations, not a causal verdict.

For this generation:
1. cite concrete current evidence for a failure or inefficiency;
2. map it to an existing or missing harness component;
3. state a falsifiable hypothesis;
4. inspect relevant MiniSWE source before editing;
5. make one coherent harness change;
6. preserve observed passing behavior where possible;
7. run proportionate local checks and `./evolve surface-check`;
8. record expected effects, risks, and the next-result decision rule.

Review prior accepted and rejected outcomes when useful, but do not claim that
trace similarity proves causality. Do not edit the Harbor adapter, evaluator,
mechanism, archive, workspace configuration, task partitions, model selection,
credentials, endpoints, or resource limits. The optional report below never
replaces the required source edit and ordinary meta-agent result.
"""

REPORT_TEMPLATE = {
    "evidence": [],
    "diagnosis": "",
    "component": "",
    "hypothesis": "",
    "changes": [],
    "expected_effects": [],
    "risks": [],
    "decision_rule": "",
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _safe_usage(usage: object) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {"usd": 0}
    normalized = dict(usage)
    usd = normalized.get("usd", 0)
    normalized["usd"] = usd if isinstance(usd, (int, float)) and not isinstance(usd, bool) else 0
    return normalized


def _surface_rules(checkout: Path) -> str:
    surface = load_surface_policy(checkout)
    return f"- Surface include: {surface.include}\n- Surface exclude: {surface.exclude}"


def build_prompt(checkout: Path, observation: str, ctx: OperatorContext) -> str:
    feedback = load_feedback(ctx.run_dir, observation)
    report_path = ctx.run_dir / "meta_agent" / "ahe-report.json"
    return (
        f"{AHE_PROMPT.rstrip()}\n\n"
        f"# Current Evidence\n\n{feedback}\n\n"
        f"# Experiment History\n\n- Archive: {ctx.workspace / 'archive.jsonl'}\n"
        f"- Prior generation artifacts: {ctx.workspace / 'runs'}\n\n"
        f"# Surface Rules\n\n{_surface_rules(checkout)}\n\n"
        f"# Optional AHE Analysis Report\n\nWrite a JSON object to `{report_path}` when possible:\n\n"
        f"```json\n{json.dumps(REPORT_TEMPLATE, indent=2)}\n```\n\n"
        "A missing or malformed report is noted but does not invalidate an otherwise valid edit.\n\n"
        "# Output Contract\n\nEdit the checkout directly. Do not output a patch instead of editing files. "
        "Make one coherent harness change and return a concise summary of checks.\n"
    )


def _report_note(path: Path) -> str:
    if not path.exists():
        return "ahe-report: missing"
    try:
        payload = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "ahe-report: malformed"
    return "ahe-report: preserved" if isinstance(payload, dict) else "ahe-report: malformed"


class AheMetaAgent(MetaAgentOperator):
    def run(self, checkout: Path, observation: str, ctx: OperatorContext) -> MetaAgentResult:
        parent_ref = patch_parent_ref(checkout, ctx)
        out = ctx.run_dir / "meta_agent"
        out.mkdir(parents=True, exist_ok=True)
        prompt = build_prompt(checkout, observation, ctx)
        (out / "prompt.md").write_text(prompt)
        try:
            agent_run = run_agent(checkout, prompt, ctx)
        except AgentCommandError as exc:
            (out / "output.txt").write_text(exc.output)
            _write_json(out / "usage.json", _safe_usage(exc.usage))
            raise SystemExit(exc.returncode)

        patch = create_candidate_patch(
            checkout=checkout,
            parent_ref=parent_ref,
            surface=load_surface_policy(checkout),
            repair=False,
        )
        usage = _safe_usage(agent_run.usage)
        notes = [
            "variant: ahe",
            f"runner: {runner_name(ctx)}",
            _report_note(out / "ahe-report.json"),
            "written-by: operators/meta_agent.py",
            *patch.notes,
        ]
        (out / "model_patch.diff").write_text(patch.diff)
        (out / "patch.diff").write_text(patch.diff)
        (out / "output.txt").write_text(agent_run.output)
        (out / "rationale.md").write_text("\n".join(notes) + "\n")
        _write_json(out / "changed.json", patch.changed_paths)
        _write_json(out / "surface-check.json", patch.surface_report)
        _write_json(out / "usage.json", usage)
        return MetaAgentResult(changed=patch.changed_paths, notes=notes, usage=usage)


if __name__ == "__main__":
    sdk.main(AheMetaAgent)
