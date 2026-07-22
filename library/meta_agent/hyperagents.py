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

MAX_INLINE_EVIDENCE_CHARS = 50_000
LATEST_DIFF_CHARS = 5_000

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


def _read_optional(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _clip_inline(text: str, source: Path, limit: int = MAX_INLINE_EVIDENCE_CHARS) -> str:
    if len(text) <= limit:
        return text
    marker = f"\n\n[inline evidence truncated; complete artifact: {source}]"
    return text[: max(limit - len(marker), 0)] + marker


def _lineage(ctx) -> str:
    return (
        "\n".join(
            "- gen %s: parent=%s score=%s status=%s"
            % (row.get("genid"), row.get("parent"), row.get("score"), row.get("status"))
            for row in sdk.rows(ctx.workspace)[-8:]
        )
        or "- No recorded generations"
    )


def _prompt_evidence(observation: str, ctx) -> str:
    selected = ctx.run_dir / "feedback" / "evidence" / "selected.md"
    attempts = ctx.run_dir / "feedback" / "attempts.md"
    current = _read_optional(selected)
    source = selected
    if not current:
        current = _read_optional(attempts)
        source = attempts
    if not current:
        current = observation.strip()

    latest_diff_path = ctx.run_dir / "feedback" / "last_accepted.diff"
    latest_diff = _read_optional(latest_diff_path)
    rendered_diff = _clip_inline(latest_diff, latest_diff_path, LATEST_DIFF_CHARS) if latest_diff else "(none)"
    return (
        f"# Current rollout evidence\n\n{_clip_inline(current, source)}\n\n"
        f"# Recent lineage\n\n{_lineage(ctx)}\n\n"
        f"# Latest accepted diff\n\n{rendered_diff}"
    )


def build_prompt(checkout: Path, observation: str, ctx) -> str:
    if runner_name(ctx) == "harbor":
        repository = Path("/app/task/workspace")
        current_run = repository / "runs" / f"gen-{ctx.genid}"
        experiment = repository
    else:
        repository = checkout
        current_run = ctx.run_dir
        experiment = ctx.workspace
    return (
        f"{PROMPT.rstrip()}\n\n"
        f"{_prompt_evidence(observation, ctx)}\n\n"
        f"Repository: {repository}\n"
        f"Feedback bundle: {current_run / 'feedback'}\n"
        f"Complete history: {current_run / 'feedback' / 'evidence' / 'history.json'}\n"
        f"Raw trace evidence: {current_run / 'trace_analyzer' / 'evidence'}\n"
        f"Archive: {experiment / 'archive.jsonl'}\n"
        f"Prior generation artifacts: {experiment / 'runs'}\n"
        f"Current generation artifacts: {current_run}\n"
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
