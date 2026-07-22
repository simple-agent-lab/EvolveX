"""HyperAgents-style self-referential meta-agent operator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evolve.agent import AgentCommandError
from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult
from evolve.patching import create_candidate_patch, load_surface_policy, patch_parent_ref
from library.meta_agent.runners import run_agent, runner_name
from library.meta_agent.support.artifacts import render_artifact_guidance

PROMPT = """# HyperAgents Self-Improvement

Modify any part of the allowed codebase to improve downstream task performance.
The benchmark directly evaluates `target/**`. Strongly prefer a substantive `target/**`
improvement in every proposal. An operator-only proposal is allowed
when evidence shows that improving the search or improvement process is higher
leverage; explain how it should benefit later target proposals. `operators/**` remains editable,
including this mutation workflow and prompt. Do not add
cosmetic target edits merely to satisfy this preference.
Inspect prior generations and evaluation artifacts before editing. Make one
coherent repository change. An operator mutation becomes active the next time
that operator is invoked: earlier-stage changes affect later generations, while
not-yet-run validation, gate, or record changes may affect this generation.
Do not modify the fixed evaluator, mechanism, workspace configuration, archive,
task partitions, credentials, endpoints, or resource limits.
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


def _remaining_iterations(ctx) -> str:
    text = (ctx.workspace / "evolve.yaml").read_text()
    maximum = next(
        (int(line.split(":", 1)[1]) for line in text.splitlines() if line.strip().startswith("max_generations:")),
        0,
    )
    current = int(str(ctx.genid).split("-", 1)[0])
    return str(max(maximum - current, 0))


def build_prompt(checkout: Path, observation: str, ctx) -> str:
    del observation
    if runner_name(ctx) == "harbor":
        repository = Path("/app/task/workspace")
        current_run = repository / "runs" / f"gen-{ctx.genid}"
        experiment = repository
    else:
        repository = checkout
        current_run = ctx.run_dir
        experiment = ctx.workspace
    feedback = current_run / "feedback"
    selected = feedback / "evidence" / "selected.md"
    latest_diff = feedback / "last_accepted.diff"
    trace_evidence = current_run / "trace_analyzer" / "evidence"
    rollout = current_run / "rollout"
    return (
        f"{PROMPT.rstrip()}\n\n"
        "# Evidence reading order\n\n"
        f"1. Read `{feedback / 'index.md'}` for the evidence map.\n"
        f"2. Read `{selected}` and `{latest_diff}` for selected findings and the latest accepted change.\n"
        f"3. Inspect relevant files under `{trace_evidence}`.\n"
        f"4. Open raw rollout artifacts under `{rollout}` only when analyzed evidence is insufficient.\n"
        "5. Edit the candidate only after reviewing the relevant evidence.\n\n"
        f"Repository: {repository}\n"
        f"Feedback bundle: {feedback}\n"
        f"Complete history: {feedback / 'evidence' / 'history.json'}\n"
        f"Raw trace evidence: {trace_evidence}\n"
        f"Archive: {experiment / 'archive.jsonl'}\n"
        f"Prior generation artifacts: {experiment / 'runs'}\n"
        f"Current generation artifacts: {current_run}\n"
        f"\n{render_artifact_guidance(ctx, experiment)}\n\n"
        f"Iterations remaining after this proposal: {_remaining_iterations(ctx)}\n\n"
        "Edit the checkout directly. Do not print a patch instead of editing files.\n"
    )


class HyperAgentsMetaAgent(MetaAgentOperator):
    def run(self, checkout: Path, observation: str, ctx) -> MetaAgentResult:
        parent_ref = patch_parent_ref(checkout, ctx)
        prompt = build_prompt(checkout, observation, ctx)
        out = ctx.run_dir / "meta_agent"
        out.mkdir(parents=True, exist_ok=True)
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
            "variant: hyperagents",
            f"runner: {runner_name(ctx)}",
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
        return MetaAgentResult(
            changed=patch.changed_paths,
            notes=notes,
            usage=usage,
        )


if __name__ == "__main__":
    sdk.main(HyperAgentsMetaAgent)
