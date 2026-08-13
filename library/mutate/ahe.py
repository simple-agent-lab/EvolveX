"""AHE strategy: turn current evidence into one testable harness change."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from evolve.agent import AgentCommandError
from evolve.frozen import sdk
from evolve.frozen.config import string
from evolve.frozen.interfaces import MutateOperator, MutateResult, OperatorContext
from evolve.patching import create_candidate_patch, load_surface_policy, patch_parent_ref
from library._shared.artifacts import render_artifact_guidance
from library._shared.runners import run_agent, runner_name
from library.mutate._config import WORKSPACE_CONFIG
from library.mutate._support.workspace import workspace_contract

MANIFEST_START = "<AHE_CHANGE_MANIFEST>"
MANIFEST_END = "</AHE_CHANGE_MANIFEST>"
MANIFEST_FILE = Path("target/.ahe-change-manifest.json")
CONFIG = WORKSPACE_CONFIG.extend(
    {
        "prompt_path": string(),
        "skills_dir": string(),
        "memory_dir": string(),
    }
)


AHE_PROMPT = """# Agentic Harness Engineering

Improve the configured candidate harness; do not solve a benchmark task directly.
Optimize pass@1. Treat debugger reports as evidence, not proof. Follow the
workspace contract and make changes only within the declared mutable surface.

For this generation:
1. Read the debugger overview and relevant task details first.
2. Read change_evaluation.json and the previous change context.
3. Decide KEEP, REVISE, or ROLLBACK + PIVOT before editing.
4. Cite specific debugger tasks and distinguish evidence from causal inference.
5. Identify the active execution path, then choose the harness component matching the root cause.
6. If the same failure survived repeated changes at one component, pivot levels.
7. Make one coherent change within the declared mutable surface and run proportionate checks.
8. Write one official-style change manifest to the required control file.

Files on the active execution path become the deployed benchmark-solving harness.
Evolution artifacts and instructions in this prompt are not available inside benchmark episodes.
If you edit a runtime prompt, include only instructions usable by the benchmark-solving agent.
Do not copy this evolution workflow, evidence
paths, KEEP/REVISE/ROLLBACK decisions, or manifest requirements into runtime files.
Do not refer to debuggers or other evolution-only context in runtime prompts.
Determine the execution path from the supplied workspace contract and evaluator configuration;
do not assume an agent class, configuration name, or repository layout.

Current debugger reports evaluate the selected parent. The new edit will be
evaluated by the next loop. Do not edit the Harbor adapter, evaluator, mechanism,
archive, workspace configuration, task partitions, model selection, credentials,
endpoints, or resource limits.
"""

CODEX_AHE_PROMPT = """# Agentic Harness Engineering

Improve the Codex harness under `target/`; do not solve a benchmark task
directly. Optimize pass@1. Treat debugger reports as evidence, not proof.

For this generation:
1. Read the debugger overview and relevant task details first.
2. Read change_evaluation.json and the previous change context.
3. Decide KEEP, REVISE, or ROLLBACK + PIVOT before editing.
4. Cite specific debugger tasks and distinguish evidence from causal inference.
5. Choose the harness component matching the root cause.
6. If the same failure survived repeated changes at one component, pivot levels.
7. Make one coherent target/** change and run proportionate checks.
8. Write one official-style change manifest to the required control file.

Files under `target/` become the deployed benchmark-solving harness. The
evolvable surface includes the runtime prompt, skills, Codex configuration, and
the local plugin under `target/plugins/`, including lifecycle hooks.
Evolution artifacts and instructions in this prompt are not available inside
benchmark episodes. If you edit runtime instructions or hook-provided context,
include only guidance usable by the benchmark-solving agent. Do not copy this
evolution workflow, evidence paths, KEEP/REVISE/ROLLBACK decisions, or manifest
requirements into target files. Do not refer to debuggers or other
evolution-only context in target runtime prompts, skills, or plugin output.
Canonical evaluation runs `target.agent:HarborAgent`, installs the candidate
plugin into a temporary Codex home, and invokes the pinned Codex CLI. Make
changes on that execution path.

Current debugger reports evaluate the selected parent. The new edit will be
evaluated by the next loop. Do not edit the evaluator, mechanism, archive,
workspace configuration, task partitions, model selection, credentials,
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
            "constraint_level": "middleware|tool_impl|tool_desc|skill|prompt|plugin|hook",
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


def _required_text(path: Path, label: str) -> str:
    try:
        text = path.read_text().strip()
    except OSError as exc:
        raise RuntimeError(f"missing {label}: {path}") from exc
    if not text:
        raise RuntimeError(f"empty {label}: {path}")
    return text


def _prior_change_context(ctx: OperatorContext) -> str:
    if ctx.parent in (None, "0"):
        return "No prior change context (baseline generation)."
    root = ctx.workspace / "runs" / f"gen-{ctx.parent}" / "mutate"
    sections = []
    for name in ("change_manifest.json", "output.txt", "changed.json", "patch.diff"):
        path = root / name
        try:
            content = path.read_text().strip()
        except OSError:
            continue
        if content:
            sections.append(f"## {name}\n\n{content[:20000]}")
    return "\n\n".join(sections) or "No prior change artifacts were preserved."


def _overview(ctx: OperatorContext) -> str:
    return _required_text(
        ctx.run_dir / "analyze" / "analysis" / "overview.md",
        "AHE debugger overview",
    )


def _evidence_paths(ctx: OperatorContext) -> str:
    root = f"runs/gen-{ctx.genid}"
    return "\n".join(
        [
            f"- Per-task details: `{root}/analyze/analysis/detail/`",
            f"- Bounded cases: `{root}/analyze/evidence/cases.jsonl`",
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
        raise ValueError("mutate output must contain exactly one AHE manifest block")
    raw = output[starts[0] + len(MANIFEST_START) : ends[0]].strip()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("AHE manifest must be a JSON object")
    if str(payload.get("iteration")) != genid:
        raise ValueError("AHE manifest iteration does not match operator context")
    if not isinstance(payload.get("changes"), list) or not payload["changes"]:
        raise ValueError("AHE manifest changes must be a nonempty list")
    return payload


def _read_manifest_file(checkout: Path, genid: str) -> dict[str, Any]:
    path = checkout / MANIFEST_FILE
    try:
        raw = path.read_text()
    except OSError as exc:
        raise ValueError(f"mutate operator must write the AHE manifest file: {MANIFEST_FILE}") from exc
    finally:
        path.unlink(missing_ok=True)
    return _extract_manifest(f"{MANIFEST_START}\n{raw}\n{MANIFEST_END}", genid)


def build_prompt(checkout: Path, observation: str, ctx: OperatorContext) -> str:
    del observation
    template = dict(MANIFEST_TEMPLATE)
    template["iteration"] = ctx.genid
    if runner_name(ctx) == "harbor":
        repository = Path("/app/task/workspace")
        current_run = repository / "runs" / f"gen-{ctx.genid}"
        experiment = repository
    else:
        repository = checkout
        current_run = ctx.run_dir
        experiment = ctx.workspace
    analysis = current_run / "analyze" / "analysis"
    overview = analysis / "overview.md"
    attribution = analysis / "change_evaluation.json"
    details = analysis / "detail"
    cases = current_run / "analyze" / "evidence" / "cases.jsonl"
    rollout = current_run / "rollout"
    if ctx.parent in (None, "0"):
        prior_change = "No selected-parent mutate change exists for this baseline generation."
    else:
        parent_mutate = experiment / "runs" / f"gen-{ctx.parent}" / "mutate"
        prior_change = (
            f"Inspect the selected parent manifest and patch. Selected parent mutate artifacts: `{parent_mutate}`"
        )
    target_prompt = CODEX_AHE_PROMPT if (checkout / "target" / "codex.toml").is_file() else AHE_PROMPT
    return (
        f"{target_prompt.rstrip()}\n\n"
        "# Evidence reading order\n\n"
        f"1. Read `{overview}`.\n"
        f"2. Read `{attribution}` and decide KEEP, REVISE, or ROLLBACK + PIVOT.\n"
        f"3. Read only the relevant per-task reports under `{details}`.\n"
        f"4. {prior_change}\n"
        f"5. Use `{cases}` and raw rollout artifacts under `{rollout}` only to resolve missing or conflicting evidence.\n"
        "6. Edit the candidate and write the required AHE change manifest.\n\n"
        "# Evidence Locations\n\n"
        f"Repository: {repository}\n"
        f"Archive: {experiment / 'archive.jsonl'}\n"
        f"Current generation artifacts: {current_run}\n"
        f"Raw trace evidence: {current_run / 'analyze' / 'evidence'}\n\n"
        f"{render_artifact_guidance(ctx, experiment)}\n\n"
        f"{workspace_contract(checkout, ctx.config, action_paths=['target'])}\n\n"
        "# Required Final Output\n\nEdit the candidate directly. After checks and before the submission action, "
        f"write the following JSON object to `{MANIFEST_FILE}`. Write JSON only; this control file is removed "
        "before the candidate patch is created. Then submit normally.\n\n"
        f"```json\n{json.dumps(template, indent=2)}\n```\n"
    )


class AheMutate(MutateOperator):
    def mutate(self, checkout: Path, observation: str, ctx: OperatorContext) -> MutateResult:
        parent_ref = patch_parent_ref(checkout, ctx)
        out = ctx.run_dir / "mutate"
        out.mkdir(parents=True, exist_ok=True)
        prompt = build_prompt(checkout, observation, ctx)
        (out / "prompt.md").write_text(prompt)
        try:
            agent_run = run_agent(checkout, prompt, ctx)
        except AgentCommandError as exc:
            (out / "output.txt").write_text(exc.output)
            _write_json(out / "usage.json", _safe_usage(exc.usage))
            raise SystemExit(exc.returncode)

        manifest_error: ValueError | None = None
        try:
            manifest = _read_manifest_file(checkout, ctx.genid)
        except ValueError as exc:
            manifest = None
            manifest_error = exc

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
        if manifest_error is not None:
            raise manifest_error
        assert manifest is not None
        _write_json(out / "change_manifest.json", manifest)
        notes = [
            "operator: ahe",
            f"runner: {runner_name(ctx)}",
            "change-manifest: parsed",
            "written-by: operators/mutate.py",
            *patch.notes,
        ]
        (out / "rationale.md").write_text("\n".join(notes) + "\n")
        return MutateResult(changed=patch.changed_paths, notes=notes, usage=usage)


if __name__ == "__main__":
    sdk.main(AheMutate, config_schema=CONFIG)
