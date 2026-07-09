"""Agent-command mutate delegates mutation to a configured meta-agent command."""

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
from evolve.frozen.interfaces import MutateOperator, MutateResult, OperatorContext
from evolve.mutation import MutationPatch, create_mutation_patch, load_surface_policy, mutation_parent_ref


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


def build_mutation_prompt(checkout: Path, observation: str, ctx: OperatorContext) -> str:
    feedback = _feedback_text(ctx.run_dir) or observation.strip()
    return (
        "\n\n".join(
            chunk
            for chunk in [
                (checkout / "operators" / "mutate.md").read_text().rstrip(),
                feedback,
                "# Surface Rules\n\n%s" % _surface_rules(checkout),
                '# Output Contract\n\nEdit the checkout directly. Do not output patches, diffs, or fenced file blocks. Optional final line: predicted_fixes: ["task-id"].',
            ]
            if chunk
        )
        + "\n"
    )


def _write_mutation_result(
    run_dir: Path,
    agent_run: AgentRunResult | None,
    patch: MutationPatch,
    notes: list[str],
    *,
    output: str = "",
    usage: dict[str, Any] | None = None,
) -> MutateResult:
    mutate_dir = run_dir / "mutate"
    mutate_dir.mkdir(parents=True, exist_ok=True)
    combined_output = output or (agent_run.output if agent_run else "")
    all_notes = [*notes, *patch.notes, "written-by: operators/mutate.py", "variant: agent_command"]
    if combined_output.strip():
        all_notes.append("agent-output: %s" % combined_output.strip().splitlines()[0])
    usage_payload = _safe_usage(usage or (agent_run.usage if agent_run else {"usd": 0}))
    _write_json(mutate_dir / "changed.json", patch.changed_paths)
    _write_json(mutate_dir / "surface-check.json", patch.surface_report)
    (mutate_dir / "patch.diff").write_text(patch.diff)
    (mutate_dir / "rationale.md").write_text("\n".join(all_notes) + "\n")
    (mutate_dir / "predicted_fixes.json").write_text(json.dumps(_predicted_fixes(combined_output)) + "\n")
    _write_json(mutate_dir / "usage.json", usage_payload)
    return MutateResult(changed=patch.changed_paths, notes=all_notes, usage=usage_payload)


def _empty_failure_patch(checkout: Path, parent_ref: str, error: Exception) -> MutationPatch:
    try:
        patch = create_mutation_patch(
            checkout=checkout,
            parent_ref=parent_ref,
            surface=load_surface_policy(checkout),
        )
    except Exception:
        patch = MutationPatch(
            changed_paths=[],
            diff="",
            surface_report={"ok": True, "mutated": [], "violations": [], "error": str(error)},
            notes=[],
        )
    return patch


class AgentCommandMutate(MutateOperator):
    def mutate(self, checkout: Path, observation: str, ctx: OperatorContext) -> MutateResult:
        parent_ref = mutation_parent_ref(checkout, ctx)
        try:
            prompt = build_mutation_prompt(checkout, observation, ctx)
            agent_run = run_meta_agent(workspace=checkout, prompt=prompt, config=ctx.config)
            patch = create_mutation_patch(
                checkout=checkout,
                parent_ref=parent_ref,
                surface=load_surface_policy(checkout),
            )
            result = _write_mutation_result(ctx.run_dir, agent_run, patch, [])
        except AgentCommandError as exc:
            patch = create_mutation_patch(
                checkout=checkout,
                parent_ref=parent_ref,
                surface=load_surface_policy(checkout),
            )
            _write_mutation_result(
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
            _write_mutation_result(ctx.run_dir, None, patch, ["error: %s" % (exc.code or "mutator exited")])
            raise SystemExit(code)
        except Exception as exc:
            patch = _empty_failure_patch(checkout, parent_ref, exc)
            _write_mutation_result(
                ctx.run_dir,
                None,
                patch,
                ["error: %s: %s" % (exc.__class__.__name__, exc)],
            )
            raise SystemExit(1)
        if not result.changed:
            return result
        surface = json.loads((ctx.run_dir / "mutate" / "surface-check.json").read_text())
        if not surface.get("ok"):
            raise SystemExit(1)
        return result


if __name__ == "__main__":
    sdk.main(AgentCommandMutate)
