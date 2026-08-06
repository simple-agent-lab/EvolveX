"""GEPA strategy: reflect on one component's trajectories and propose an edit."""

# ruff: noqa: E402

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evolve.agent import AgentCommandError
from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult, OperatorContext
from evolve.patching import create_candidate_patch, load_surface_policy, patch_parent_ref
from library.gepa_support import component_paths, path_in_scopes, read_json, selected_component_names
from library.meta_agent.runners import run_agent, runner_name
from library.meta_agent.support.artifacts import render_artifact_guidance
from library.meta_agent.support.workspace import workspace_contract

GEPA_PROMPT = """# GEPA Reflective Mutation

Improve the live candidate using reflective feedback from its executions.
Read the proposal inputs from the files listed below, inspect the candidate,
and edit the checkout directly. Preserve behavior that worked. Do not encode
benchmark answers or change the evaluator, dataset, splits, Harbor adapter,
mechanism, credentials, endpoint, model, or resource limits.

Treat `Feedback.natural_language_feedback` in each reflective example as the
primary evaluator signal. Absorb its concrete prose critique into the mutation
hypothesis. The execution reward is only a protocol completion signal; it is not
a quality score and must not replace the natural-language feedback.

When a component path is a skill directory, treat the whole directory as one
component: `SKILL.md` is its required entrypoint, while `references/`,
`scripts/`, `assets/`, and `agents/openai.yaml` are bundled behavior resources.
Inspect existing resources and add, update, or remove them coherently with the
entrypoint. Run any changed scripts before finishing.
"""


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


def _agent_path(path: Path, ctx: OperatorContext) -> str:
    if runner_name(ctx) == "harbor":
        for root in (ctx.checkout, ctx.workspace):
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                continue
            return f"/app/task/workspace/{relative}"
        raise ValueError(f"GEPA agent input path is outside the candidate and workspace: {path}")
    return str(path.resolve())


def build_prompt(checkout: Path, ctx: OperatorContext) -> tuple[str, dict[str, Any]]:
    components = component_paths(ctx.config)
    selected = selected_component_names(ctx.config, ctx.genid)
    evidence_root = ctx.run_dir / "trace_analyzer" / "evidence"
    manifest_path = evidence_root / "manifest.json"
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("component_evidence"), dict):
        raise ValueError(f"missing GEPA component evidence manifest: {manifest_path}")
    component_evidence = manifest["component_evidence"]
    evidence_files: dict[str, str] = {}
    example_counts: dict[str, int] = {}
    for name in selected:
        entry = component_evidence.get(name)
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise ValueError(f"missing GEPA evidence for component {name!r}: {manifest_path}")
        evidence_path = evidence_root / entry["file"]
        if not evidence_path.is_file():
            raise ValueError(f"missing GEPA component evidence: {evidence_path}")
        evidence_files[name] = _agent_path(evidence_path, ctx)
        example_counts[name] = int(entry.get("records") or 0)
    focus_paths = [path for name in selected for path in components[name]]
    required_placeholders = ctx.config.get("required_placeholders") or []
    if not isinstance(required_placeholders, list) or not all(
        isinstance(value, str) and value for value in required_placeholders
    ):
        raise ValueError("required_placeholders must be a list of non-empty strings")
    if path_in_scopes("target/prompt.md", focus_paths) and "{{ instruction }}" not in required_placeholders:
        required_placeholders.append("{{ instruction }}")
    placeholder_rule = (
        "Preserve these literal template expressions: "
        + ", ".join(f"`{value}`" for value in required_placeholders)
        + "."
        if required_placeholders
        else ""
    )
    experiment = Path("/app/task/workspace") if runner_name(ctx) == "harbor" else ctx.workspace
    component_inputs = "\n".join(
        f"- `{name}` evidence: `{evidence_files[name]}`\n"
        f"  Candidate focus paths: {', '.join(f'`{path}`' for path in components[name])}"
        for name in selected
    )
    prompt = (
        f"{GEPA_PROMPT.rstrip()}\n\n"
        f"{workspace_contract(checkout, ctx.config)}\n\n"
        "## Inputs\n\n"
        "Read these files before deciding what to change:\n\n"
        f"1. Evidence manifest: `{_agent_path(manifest_path, ctx)}`\n"
        f"2. Selected component evidence:\n{component_inputs}\n"
        f"3. Inspect the live candidate under `{_agent_path(checkout / 'target', ctx)}`. "
        "Start with the candidate focus paths above, then inspect related target files when useful.\n\n"
        f"{placeholder_rule}\n\n"
        f"{render_artifact_guidance(ctx, experiment)}\n\n"
        "## Required action\n\n"
        "1. Compare high- and low-reward trajectories and verifier feedback.\n"
        "2. Infer a transferable lesson and make one coherent improvement to the live candidate.\n"
        "3. You may modify any file allowed by the candidate workspace contract.\n"
        "4. Run proportionate checks, verify the diff, and summarize the hypothesis and expected effect.\n"
    )
    proposal = {
        "parent": ctx.parent,
        "components": selected,
        "paths": focus_paths,
        "evidence_manifest": manifest_path.relative_to(ctx.workspace).as_posix(),
        "evidence_files": {
            name: (evidence_root / component_evidence[name]["file"]).relative_to(ctx.workspace).as_posix()
            for name in selected
        },
        "example_counts": example_counts,
    }
    return prompt, proposal


class GepaMetaAgent(MetaAgentOperator):
    def run(self, checkout: Path, observation: str, ctx: OperatorContext) -> MetaAgentResult:
        del observation
        parent_ref = patch_parent_ref(checkout, ctx)
        out = ctx.run_dir / "meta_agent"
        out.mkdir(parents=True, exist_ok=True)
        prompt, proposal = build_prompt(checkout, ctx)
        (out / "prompt.md").write_text(prompt)
        _write_json(out / "proposal.json", proposal)
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
        violations = list(patch.surface_report.get("violations") or [])
        usage = _safe_usage(agent_run.usage)
        (out / "model_patch.diff").write_text(patch.diff)
        (out / "patch.diff").write_text(patch.diff)
        (out / "output.txt").write_text(agent_run.output)
        _write_json(out / "changed.json", patch.changed_paths)
        _write_json(out / "surface-check.json", patch.surface_report)
        _write_json(out / "usage.json", usage)
        if violations:
            raise SystemExit("GEPA meta-agent changed paths outside the mutable surface: " + ", ".join(violations))
        notes = [
            "variant: gepa",
            f"runner: {runner_name(ctx)}",
            "components: " + ", ".join(proposal["components"]),
            "written-by: operators/meta_agent.py",
            *patch.notes,
        ]
        (out / "rationale.md").write_text("\n".join(notes) + "\n")
        return MetaAgentResult(changed=patch.changed_paths, notes=notes, usage=usage)


if __name__ == "__main__":
    sdk.main(GepaMetaAgent)
