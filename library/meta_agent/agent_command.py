"""Agent-command meta-agent delegates candidate edits to a configured command."""

# ruff: noqa: E402

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.agent import AgentCommandError, AgentRunResult, run_meta_agent
from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult, OperatorContext
from evolve.patching import CandidatePatch, create_candidate_patch, load_surface_policy, patch_parent_ref

_RUNTIME_GUIDANCE = (
    "# Optional Runtime Feedback\n\n"
    "When runtime uncertainty is relevant, run `./evolve candidate-smoke --full`. Read its stdout/stderr artifacts, "
    "repair the candidate environment with the candidate's own tools, and rerun smoke. Do not edit evaluator-owned "
    "files."
)


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


def _feedback_text(run_dir: Path) -> str:
    root = (run_dir / "feedback").resolve()
    index = root / "index.md"
    seen: set[Path] = set()
    parts: list[tuple[str, str]] = []
    if index.exists():
        text = index.read_text()
        parts.append(("feedback/index.md", text))
        seen.add(index.resolve())
        for rel in re.findall(r"\[[^\]]+\]\(([^)#]+)", text):
            path = (root / rel.strip()).resolve()
            if path.is_file() and (path == root or root in path.parents) and path not in seen:
                parts.append((f"feedback/{path.relative_to(root).as_posix()}", path.read_text()))
                seen.add(path)
    rules = root / "rules.md"
    if rules.exists() and rules.resolve() not in seen:
        parts.append(("feedback/rules.md", rules.read_text()))
    return "\n".join("## %s\n%s" % (name, text.rstrip()) for name, text in parts if text.strip())


def _surface_rules(checkout: Path) -> str:
    surface = load_surface_policy(checkout)
    return "- Surface include: %s\n- Surface exclude: %s" % (surface.include, surface.exclude)


def _experiment_config(checkout: Path) -> str:
    path = checkout / "evolve.yaml"
    if not path.exists():
        return ""
    return "# Experiment Config\n\n```yaml\n%s\n```" % path.read_text().rstrip()


def _evidence_contract() -> str:
    return (
        "# Evidence Contract\n\n"
        "You are editing the MiniSWE source checkout under `target/`, not wrapping a CLI. "
        "Use source-code changes that can be committed inside the mutable surface. Before changing files, identify:\n\n"
        "1. Failure evidence: which task behavior or feedback motivates the edit.\n"
        "2. Root cause: why the current MiniSWE source likely failed.\n"
        "3. Targeted fix: the smallest source change that addresses that root cause.\n"
        "4. Predicted impact: final output must include `predicted_fixes: [...]`; include `risk_tasks: [...]` if known.\n"
    )


def build_meta_agent_prompt(checkout: Path, observation: str, ctx: OperatorContext) -> str:
    feedback = _feedback_text(ctx.run_dir) or observation.strip()
    strategy = (checkout / "operators" / "meta_agent.md").read_text().rstrip()
    runtime_guidance = "" if "candidate-smoke" in strategy else _RUNTIME_GUIDANCE
    return (
        "\n\n".join(
            chunk
            for chunk in [
                strategy,
                _experiment_config(checkout),
                feedback,
                _evidence_contract(),
                runtime_guidance,
                "# Surface Rules\n\n%s" % _surface_rules(checkout),
                '# Output Contract\n\nEdit the checkout directly. Do not output patches, diffs, or fenced file blocks. Optional final line: predicted_fixes: ["task-id"].',
            ]
            if chunk
        )
        + "\n"
    )


def _write_meta_agent_result(
    run_dir: Path,
    agent_run: AgentRunResult | None,
    patch: CandidatePatch,
    notes: list[str],
    *,
    output: str = "",
    usage: dict[str, Any] | None = None,
) -> MetaAgentResult:
    meta_agent_dir = run_dir / "meta_agent"
    meta_agent_dir.mkdir(parents=True, exist_ok=True)
    combined_output = output or (agent_run.output if agent_run else "")
    all_notes = [*notes, *patch.notes, "written-by: operators/meta_agent.py", "variant: agent_command"]
    if combined_output.strip():
        all_notes.append("agent-output: %s" % combined_output.strip().splitlines()[0])
    usage_payload = _safe_usage(usage or (agent_run.usage if agent_run else {"usd": 0}))
    _write_json(meta_agent_dir / "changed.json", patch.changed_paths)
    _write_json(meta_agent_dir / "surface-check.json", patch.surface_report)
    (meta_agent_dir / "patch.diff").write_text(patch.diff)
    (meta_agent_dir / "rationale.md").write_text("\n".join(all_notes) + "\n")
    (meta_agent_dir / "predicted_fixes.json").write_text(json.dumps(_predicted_fixes(combined_output)) + "\n")
    _write_json(meta_agent_dir / "usage.json", usage_payload)
    return MetaAgentResult(changed=patch.changed_paths, notes=all_notes, usage=usage_payload)


def _empty_failure_patch(checkout: Path, parent_ref: str, error: Exception) -> CandidatePatch:
    try:
        patch = create_candidate_patch(
            checkout=checkout,
            parent_ref=parent_ref,
            surface=load_surface_policy(checkout),
        )
    except Exception:
        patch = CandidatePatch(
            changed_paths=[],
            diff="",
            surface_report={"ok": True, "mutated": [], "violations": [], "error": str(error)},
            notes=[],
        )
    return patch


class AgentCommandMetaAgent(MetaAgentOperator):
    def run(self, checkout: Path, observation: str, ctx: OperatorContext) -> MetaAgentResult:
        parent_ref = patch_parent_ref(checkout, ctx)
        try:
            prompt = build_meta_agent_prompt(checkout, observation, ctx)
            agent_run = run_meta_agent(workspace=checkout, prompt=prompt, config=ctx.config)
            patch = create_candidate_patch(
                checkout=checkout,
                parent_ref=parent_ref,
                surface=load_surface_policy(checkout),
            )
            result = _write_meta_agent_result(ctx.run_dir, agent_run, patch, [])
        except AgentCommandError as exc:
            patch = create_candidate_patch(
                checkout=checkout,
                parent_ref=parent_ref,
                surface=load_surface_policy(checkout),
            )
            _write_meta_agent_result(
                ctx.run_dir,
                None,
                patch,
                ["error: %s" % exc],
                output=exc.output,
                usage=exc.usage,
            )
            raise SystemExit(exc.returncode)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) and exc.code else 1
            patch = _empty_failure_patch(checkout, parent_ref, exc)
            _write_meta_agent_result(ctx.run_dir, None, patch, ["error: %s" % (exc.code or "meta-agent exited")])
            raise SystemExit(code)
        except Exception as exc:
            patch = _empty_failure_patch(checkout, parent_ref, exc)
            _write_meta_agent_result(
                ctx.run_dir,
                None,
                patch,
                ["error: %s: %s" % (exc.__class__.__name__, exc)],
            )
            raise SystemExit(1)
        if not result.changed:
            return result
        surface = json.loads((ctx.run_dir / "meta_agent" / "surface-check.json").read_text())
        if not surface.get("ok"):
            raise SystemExit(1)
        return result


if __name__ == "__main__":
    sdk.main(AgentCommandMetaAgent)
