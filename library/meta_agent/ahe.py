"""AHE strategy: turn current evidence into one testable harness change."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from evolve.agent import AgentCommandError
from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult, OperatorContext
from evolve.patching import create_candidate_patch, load_surface_policy, patch_parent_ref
from library.meta_agent.runners import run_agent, runner_name

MANIFEST_START = "<AHE_CHANGE_MANIFEST>"
MANIFEST_END = "</AHE_CHANGE_MANIFEST>"

AHE_PROMPT = """# Agentic Harness Engineering

Improve the MiniSWE harness under `target/`; do not solve a benchmark task
directly. Optimize pass@1. Treat debugger reports as evidence, not proof.

For this generation:
1. Read the debugger overview and relevant task details first.
2. Read change_evaluation.json and the previous change manifest.
3. Decide KEEP, REVISE, or ROLLBACK + PIVOT before editing.
4. Cite specific debugger tasks and distinguish evidence from causal inference.
5. Choose the harness component matching the root cause.
6. If the same failure survived repeated changes at one component, pivot levels.
7. Make one coherent target/** change and run proportionate checks.
8. End with one delimited official-style change manifest describing the changes.

Current debugger reports evaluate the selected parent. The new edit will be
evaluated by the next loop. Do not edit the Harbor adapter, evaluator, mechanism,
archive, workspace configuration, task partitions, model selection, credentials,
endpoints, or resource limits.
"""

MANIFEST_TEMPLATE = {
    "iteration": 1,
    "changes": [
        {
            "id": "chg-1",
            "type": "new|improvement|rollback",
            "description": "what changed and why",
            "files": ["target/path.py"],
            "failure_pattern": "failure class addressed",
            "predicted_fixes": ["task-name"],
            "risk_tasks": [],
            "constraint_level": "middleware|tool_impl|tool_desc|skill|prompt",
            "why_this_component": "why this component level fits the root cause",
        }
    ],
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


def _required_text(path: Path, label: str) -> str:
    try:
        text = path.read_text().strip()
    except OSError as exc:
        raise RuntimeError(f"missing {label}: {path}") from exc
    if not text:
        raise RuntimeError(f"empty {label}: {path}")
    return text


def _prior_manifest(ctx: OperatorContext) -> str:
    if ctx.parent in (None, "0"):
        return "No prior change manifest (baseline generation)."
    path = ctx.workspace / "runs" / f"gen-{ctx.parent}" / "meta_agent" / "change_manifest.json"
    return _required_text(path, "prior AHE change manifest")


def _overview(ctx: OperatorContext) -> str:
    return _required_text(
        ctx.run_dir / "trace_analyzer" / "analysis" / "overview.md",
        "AHE debugger overview",
    )


def _evidence_paths(ctx: OperatorContext) -> str:
    root = f"runs/gen-{ctx.genid}"
    return "\n".join(
        [
            f"- Per-task details: `{root}/trace_analyzer/analysis/detail/`",
            f"- Bounded cases: `{root}/trace_analyzer/evidence/cases.jsonl`",
            f"- Raw rollout artifacts: `{root}/rollout/`",
        ]
    )


def _recent_archive(ctx: OperatorContext) -> str:
    path = ctx.workspace / "archive.jsonl"
    if not path.is_file():
        return "(archive not created yet)"
    return "\n".join(path.read_text().splitlines()[-20:])


def _extract_manifest(output: str, genid: str) -> dict[str, Any]:
    starts = [match.start() for match in re.finditer(re.escape(MANIFEST_START), output)]
    ends = [match.start() for match in re.finditer(re.escape(MANIFEST_END), output)]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        raise ValueError("meta-agent output must contain exactly one AHE manifest block")
    raw = output[starts[0] + len(MANIFEST_START) : ends[0]].strip()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("AHE manifest must be a JSON object")
    if str(payload.get("iteration")) != genid:
        raise ValueError("AHE manifest iteration does not match operator context")
    if not isinstance(payload.get("changes"), list) or not payload["changes"]:
        raise ValueError("AHE manifest changes must be a nonempty list")
    return payload


def build_prompt(checkout: Path, observation: str, ctx: OperatorContext) -> str:
    del observation
    attribution = _required_text(
        ctx.run_dir / "trace_analyzer" / "analysis" / "change_evaluation.json",
        "AHE change evaluation",
    )
    template = dict(MANIFEST_TEMPLATE)
    template["iteration"] = int(ctx.genid)
    return (
        f"{AHE_PROMPT.rstrip()}\n\n"
        f"# Current Debugger Overview\n\n{_overview(ctx)}\n\n"
        f"# Evidence Paths\n\n{_evidence_paths(ctx)}\n\n"
        f"# Change Attribution\n\n```json\n{attribution}\n```\n\n"
        f"# Previous Change Manifest\n\n```json\n{_prior_manifest(ctx)}\n```\n\n"
        f"# Recent Archive Outcomes\n\n```jsonl\n{_recent_archive(ctx)}\n```\n\n"
        f"# Surface Rules\n\n{_surface_rules(checkout)}\n\n"
        "# Required Final Output\n\nEdit the candidate directly. After the concise summary, emit exactly one block:\n\n"
        f"{MANIFEST_START}\n{json.dumps(template, indent=2)}\n{MANIFEST_END}\n"
    )


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
        (out / "model_patch.diff").write_text(patch.diff)
        (out / "patch.diff").write_text(patch.diff)
        (out / "output.txt").write_text(agent_run.output)
        _write_json(out / "changed.json", patch.changed_paths)
        _write_json(out / "surface-check.json", patch.surface_report)
        _write_json(out / "usage.json", usage)
        manifest = _extract_manifest(agent_run.output, ctx.genid)
        _write_json(out / "change_manifest.json", manifest)
        notes = [
            "variant: ahe",
            f"runner: {runner_name(ctx)}",
            "change-manifest: parsed",
            "written-by: operators/meta_agent.py",
            *patch.notes,
        ]
        (out / "rationale.md").write_text("\n".join(notes) + "\n")
        return MetaAgentResult(changed=patch.changed_paths, notes=notes, usage=usage)


if __name__ == "__main__":
    sdk.main(AheMetaAgent)
