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

GEPA_PROMPT = """# GEPA Reflective Mutation

Improve an agent component using the supplied execution examples. Each example
contains the task input, the agent's generated messages and ordered tool
trajectory, verifier feedback, and reward.

Infer a concise, transferable lesson across examples, inspect the current
component, and edit only the selected component paths. Preserve behavior that
worked. Do not encode benchmark answers or change the evaluator, dataset,
splits, Harbor adapter, mechanism, credentials, endpoint, model, or resource
limits. Edit the checkout directly and run proportionate checks.
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


def _component_snapshot(checkout: Path, scopes: list[str], limit: int) -> str:
    chunks: list[str] = []
    remaining = limit
    for scope in scopes:
        root = checkout / scope
        paths = (
            [root]
            if root.is_file()
            else sorted(path for path in root.rglob("*") if path.is_file())
            if root.is_dir()
            else []
        )
        for path in paths:
            if path.is_symlink():
                continue
            try:
                text = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            relative = path.relative_to(checkout).as_posix()
            rendered = f"### `{relative}`\n\n```text\n{text}\n```\n"
            chunks.append(rendered[:remaining])
            remaining -= min(len(rendered), remaining)
            if remaining <= 0:
                return "\n".join(chunks) + "\n...[component snapshot truncated]...\n"
    return "\n".join(chunks) or "(selected component does not currently exist)"


def build_prompt(checkout: Path, ctx: OperatorContext) -> tuple[str, dict[str, Any]]:
    components = component_paths(ctx.config)
    selected = selected_component_names(ctx.config, ctx.genid)
    dataset_path = ctx.run_dir / "trace_analyzer" / "evidence" / "reflective_dataset.json"
    payload = read_json(dataset_path)
    if not isinstance(payload, dict):
        raise ValueError(f"missing GEPA reflective dataset: {dataset_path}")
    selected_dataset = {name: payload.get(name, []) if isinstance(payload.get(name), list) else [] for name in selected}
    max_examples = max(1, int(ctx.config.get("max_examples", 16)))
    selected_dataset = {name: records[:max_examples] for name, records in selected_dataset.items()}
    max_dataset_chars = max(1, int(ctx.config.get("dataset_chars", 60000)))
    rendered_dataset = json.dumps(selected_dataset, indent=2, sort_keys=True)
    if len(rendered_dataset) > max_dataset_chars:
        rendered_dataset = rendered_dataset[:max_dataset_chars] + "\n...[reflective dataset truncated]..."
    scopes = [path for name in selected for path in components[name]]
    snapshot = _component_snapshot(checkout, scopes, max(1, int(ctx.config.get("component_chars", 30000))))
    required_placeholders = ctx.config.get("required_placeholders") or []
    if not isinstance(required_placeholders, list) or not all(
        isinstance(value, str) and value for value in required_placeholders
    ):
        raise ValueError("required_placeholders must be a list of non-empty strings")
    if path_in_scopes("target/prompt.md", scopes) and "{{ instruction }}" not in required_placeholders:
        required_placeholders.append("{{ instruction }}")
    placeholder_rule = (
        "Preserve these literal template expressions: "
        + ", ".join(f"`{value}`" for value in required_placeholders)
        + "."
        if required_placeholders
        else ""
    )
    prompt = (
        f"{GEPA_PROMPT.rstrip()}\n\n"
        f"## Selected component\n\n{', '.join(f'`{name}`' for name in selected)}\n\n"
        f"Allowed paths: {', '.join(f'`{path}`' for path in scopes)}\n\n"
        f"{placeholder_rule}\n\n"
        f"## Current component\n\n{snapshot}\n\n"
        f"## Reflective dataset\n\n```json\n{rendered_dataset}\n```\n\n"
        "## Required action\n\n"
        "1. Compare high- and low-reward trajectories and verifier feedback.\n"
        "2. State a general lesson internally, then make one coherent component edit.\n"
        "3. Do not edit paths outside the allowed paths.\n"
        "4. Verify the diff and summarize the hypothesis and expected effect.\n"
    )
    proposal = {
        "parent": ctx.parent,
        "components": selected,
        "paths": scopes,
        "reflective_dataset": dataset_path.relative_to(ctx.workspace).as_posix(),
        "example_counts": {name: len(records) for name, records in selected_dataset.items()},
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
        scopes = list(proposal["paths"])
        violations = [path for path in patch.changed_paths if not path_in_scopes(path, scopes)]
        usage = _safe_usage(agent_run.usage)
        (out / "model_patch.diff").write_text(patch.diff)
        (out / "patch.diff").write_text(patch.diff)
        (out / "output.txt").write_text(agent_run.output)
        _write_json(out / "changed.json", patch.changed_paths)
        _write_json(out / "surface-check.json", patch.surface_report)
        _write_json(out / "component-scope-check.json", {"ok": not violations, "violations": violations})
        _write_json(out / "usage.json", usage)
        if violations:
            raise SystemExit("GEPA meta-agent changed paths outside the selected component: " + ", ".join(violations))
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
