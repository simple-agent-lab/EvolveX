"""HyperAgents-style self-referential meta-agent operator."""

# ruff: noqa: E402

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.agent import AgentCommandError, run_meta_agent
from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult
from evolve.patching import create_candidate_patch, load_surface_policy, patch_parent_ref


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


def build_prompt(checkout: Path, ctx) -> str:
    strategy = (checkout / "operators" / "meta_agent.md").read_text().rstrip()
    return (
        f"{strategy}\n\n"
        f"Repository: {checkout}\n"
        f"Archive: {ctx.workspace / 'archive.jsonl'}\n"
        f"Prior generation artifacts: {ctx.workspace / 'runs'}\n"
        f"Current generation artifacts: {ctx.run_dir}\n"
        f"Iterations remaining after this proposal: {_remaining_iterations(ctx)}\n\n"
        "Edit the checkout directly. Do not print a patch instead of editing files.\n"
    )


class HyperAgentsMetaAgent(MetaAgentOperator):
    def run(self, checkout: Path, observation: str, ctx) -> MetaAgentResult:
        parent_ref = patch_parent_ref(checkout, ctx)
        prompt = build_prompt(checkout, ctx)
        out = ctx.run_dir / "meta_agent"
        out.mkdir(parents=True, exist_ok=True)
        (out / "prompt.md").write_text(prompt)
        try:
            agent_run = run_meta_agent(workspace=checkout, prompt=prompt, config=ctx.config)
        except AgentCommandError as exc:
            (out / "output.txt").write_text(exc.output)
            _write_json(out / "usage.json", _safe_usage(exc.usage))
            raise SystemExit(exc.returncode)

        patch = create_candidate_patch(
            checkout=checkout,
            parent_ref=parent_ref,
            surface=load_surface_policy(checkout),
        )
        usage = _safe_usage(agent_run.usage)
        notes = ["written-by: operators/meta_agent.py", "variant: hyperagents", *patch.notes]

        (out / "model_patch.diff").write_text(patch.diff)
        (out / "patch.diff").write_text(patch.diff)
        (out / "output.txt").write_text(agent_run.output)
        (out / "rationale.md").write_text("\n".join(notes) + "\n")
        (out / "predicted_fixes.json").write_text("[]\n")
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
