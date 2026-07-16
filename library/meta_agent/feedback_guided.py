"""Use rollout-derived feedback to make one targeted candidate improvement."""

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

from evolve.agent import AgentCommandError, AgentRunResult
from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult, OperatorContext
from evolve.patching import CandidatePatch, create_candidate_patch, load_surface_policy, patch_parent_ref
from library.meta_agent.runners import run_agent, runner_name
from library.meta_agent.support.evidence import load_feedback


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


def _predicted_fixes(text: str) -> list[Any]:
    for line in text.splitlines():
        if line.strip().startswith("predicted_fixes:"):
            try:
                value = json.loads(line.split(":", 1)[1].strip())
            except Exception:
                return []
            return value if isinstance(value, list) else []
    return []


def build_prompt(checkout: Path, observation: str, ctx: OperatorContext) -> str:
    feedback = load_feedback(ctx.run_dir, observation)
    surface = load_surface_policy(checkout)
    return (
        "\n\n".join(
            chunk
            for chunk in [
                (checkout / "operators" / "meta_agent.md").read_text().rstrip(),
                feedback,
                "# Surface Rules\n\n- Surface include: %s\n- Surface exclude: %s" % (surface.include, surface.exclude),
                '# Output Contract\n\nEdit the checkout directly. Do not output patches, diffs, or fenced file blocks. Optional final line: predicted_fixes: ["task-id"].',
            ]
            if chunk
        )
        + "\n"
    )


def _write_result(
    run_dir: Path,
    agent_run: AgentRunResult | None,
    patch: CandidatePatch,
    notes: list[str],
    *,
    output: str = "",
    usage: dict[str, Any] | None = None,
) -> MetaAgentResult:
    root = run_dir / "meta_agent"
    root.mkdir(parents=True, exist_ok=True)
    combined_output = output or (agent_run.output if agent_run else "")
    all_notes = ["variant: feedback_guided", *notes, *patch.notes, "written-by: operators/meta_agent.py"]
    if combined_output.strip():
        all_notes.append("agent-output: %s" % combined_output.strip().splitlines()[0])
    usage_payload = _safe_usage(usage or (agent_run.usage if agent_run else {"usd": 0}))
    _write_json(root / "changed.json", patch.changed_paths)
    _write_json(root / "surface-check.json", patch.surface_report)
    (root / "patch.diff").write_text(patch.diff)
    (root / "rationale.md").write_text("\n".join(all_notes) + "\n")
    (root / "predicted_fixes.json").write_text(json.dumps(_predicted_fixes(combined_output)) + "\n")
    _write_json(root / "usage.json", usage_payload)
    return MetaAgentResult(changed=patch.changed_paths, notes=all_notes, usage=usage_payload)


def _failure_patch(checkout: Path, parent_ref: str, error: Exception) -> CandidatePatch:
    try:
        return create_candidate_patch(
            checkout=checkout,
            parent_ref=parent_ref,
            surface=load_surface_policy(checkout),
        )
    except Exception:
        return CandidatePatch(
            changed_paths=[],
            diff="",
            surface_report={"ok": True, "mutated": [], "violations": [], "error": str(error)},
            notes=[],
        )


class FeedbackGuidedMetaAgent(MetaAgentOperator):
    def run(self, checkout: Path, observation: str, ctx: OperatorContext) -> MetaAgentResult:
        parent_ref = patch_parent_ref(checkout, ctx)
        try:
            prompt = build_prompt(checkout, observation, ctx)
            agent_run = run_agent(checkout, prompt, ctx)
            patch = create_candidate_patch(
                checkout=checkout,
                parent_ref=parent_ref,
                surface=load_surface_policy(checkout),
            )
            return _write_result(
                ctx.run_dir,
                agent_run,
                patch,
                [f"runner: {runner_name(ctx)}"],
            )
        except AgentCommandError as exc:
            patch = _failure_patch(checkout, parent_ref, exc)
            _write_result(
                ctx.run_dir,
                None,
                patch,
                [f"error: {exc}", f"runner: {runner_name(ctx)}"],
                output=exc.output,
                usage=exc.usage,
            )
            raise SystemExit(exc.returncode)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) and exc.code else 1
            patch = _failure_patch(checkout, parent_ref, exc)
            _write_result(ctx.run_dir, None, patch, [f"error: {exc.code or 'meta-agent exited'}"])
            raise SystemExit(code)
        except Exception as exc:
            patch = _failure_patch(checkout, parent_ref, exc)
            _write_result(ctx.run_dir, None, patch, [f"error: {exc.__class__.__name__}: {exc}"])
            raise SystemExit(1)


if __name__ == "__main__":
    sdk.main(FeedbackGuidedMetaAgent)
