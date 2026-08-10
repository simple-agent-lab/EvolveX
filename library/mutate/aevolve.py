"""A-Evolve strategy: distill recent task observations into workspace updates."""

# ruff: noqa: E402

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from evolve.agent import AgentCommandError
from evolve.frozen import sdk
from evolve.frozen.interfaces import MutateOperator, MutateResult, OperatorContext
from evolve.patching import create_candidate_patch, load_surface_policy, patch_parent_ref
from library._shared.config import (
    boolean,
    config_object,
    mapping,
    nonnegative_int,
    positive_int,
    reject_unknown,
    string,
    string_list,
)
from library.mutate._runners import run_agent, runner_name
from library.mutate._support.artifacts import render_artifact_guidance
from library.mutate._support.evidence import load_feedback
from library.mutate._support.workspace import workspace_contract

DEFAULT_INLINE_EVIDENCE_CHARS = 50_000
TRAJECTORY_ONLY_OPERATOR = "trajectory_only"
_RUNNER_KEYS = {
    "runner",
    "command",
    "agent",
    "model",
    "environment",
    "environment_kwargs",
    "image",
    "workdir",
    "agent_kwargs",
    "agent_env",
    "agent_pythonpath",
    "jobs_dir",
}
_CONFIG_KEYS = _RUNNER_KEYS | {
    "trajectory_only",
    "expose_gate_data",
    "editable_roots",
    "evolve_prompts",
    "evolve_skills",
    "evolve_memory",
    "prompt_path",
    "skills_dir",
    "memory_dir",
    "history_cycles",
    "max_observations",
    "feedback_chars",
    "evidence_chars",
    "required_placeholders",
    "max_retries",
}


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, _CONFIG_KEYS)
    normalized = _runner_config(config)
    normalized.update(
        {
            "trajectory_only": boolean(config, "trajectory_only", False),
            "expose_gate_data": boolean(config, "expose_gate_data", False),
            "editable_roots": string_list(config, "editable_roots", ["target"]),
            "evolve_prompts": boolean(config, "evolve_prompts", True),
            "evolve_skills": boolean(config, "evolve_skills", True),
            "evolve_memory": boolean(config, "evolve_memory", True),
            "history_cycles": positive_int(config, "history_cycles", 2),
            "max_observations": positive_int(config, "max_observations", 30),
            "feedback_chars": positive_int(config, "feedback_chars", 300),
            "evidence_chars": positive_int(config, "evidence_chars", DEFAULT_INLINE_EVIDENCE_CHARS),
            "max_retries": nonnegative_int(config, "max_retries", 0),
        }
    )
    for key in ("prompt_path", "skills_dir", "memory_dir"):
        if key in config:
            normalized[key] = string(config, key, "")
    if "required_placeholders" in config:
        normalized["required_placeholders"] = string_list(config, "required_placeholders", [])
    return normalized


def _runner_config(config: dict[str, object]) -> dict[str, object]:
    runner = string(config, "runner", "local")
    if runner not in {"local", "harbor"}:
        raise ValueError("runner must be 'local' or 'harbor'")
    normalized: dict[str, object] = {"runner": runner}
    for key in ("command", "agent", "model", "environment", "image", "workdir", "agent_pythonpath", "jobs_dir"):
        if key in config:
            normalized[key] = string(config, key, "")
    for key in ("environment_kwargs", "agent_kwargs", "agent_env"):
        if key in config:
            normalized[key] = mapping(config, key, {})
    return normalized


AEVOLVE_SYSTEM_PROMPT = """# A-Evolve Workspace Improvement

You are a meta-learning agent that improves another agent by modifying its
workspace files. Analyze recent task observations, identify recurring failure
patterns and transferable lessons, review draft skills, and make precise
workspace edits that should improve future task performance.

Guidelines:
- Quality over quantity. Only create skills that genuinely help future tasks.
- Treat each skill as one self-contained directory. Keep `SKILL.md` as its
  required entrypoint and evolve `references/`, `scripts/`, `assets/`, or
  `agents/openai.yaml` when those resources make the behavior more reliable.
- Keep detailed knowledge in references, repeatable deterministic work in
  scripts, and output material in assets. Ensure `SKILL.md` tells the agent
  when to read or invoke each bundled resource.
- Keep memory concise and actionable when memory evolution is enabled.
- Preserve unrelated behavior and do not encode benchmark-specific answers.
- Inspect existing files before editing and verify the final diff.
- Do not modify the evaluator, mechanism, archive, task partitions,
  credentials, endpoints, model selection, or resource limits.
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


def _positive_int(value: object, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _enabled(config: dict[str, Any], key: str, default: bool) -> bool:
    value = config.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _relative_path(checkout: Path, value: object, default: str) -> tuple[Path, str]:
    relative = Path(str(value or default))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"A-Evolve workspace path must be checkout-relative: {relative}")
    resolved = (checkout / relative).resolve()
    root = checkout.resolve()
    if root not in resolved.parents:
        raise ValueError(f"A-Evolve workspace path escaped the checkout: {relative}")
    return resolved, relative.as_posix()


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _case_feedback(case: dict[str, Any], limit: int) -> str:
    verifier = str(case.get("verifier_output") or "").strip()
    exception = case.get("exception")
    if isinstance(exception, dict):
        exception_text = ": ".join(
            str(value).strip() for value in (exception.get("type"), exception.get("message")) if value
        )
    else:
        exception_text = ""
    text = verifier or exception_text or str(case.get("outcome") or "unknown")
    return text[:limit]


def _case_summaries(ctx: OperatorContext) -> list[dict[str, Any]]:
    history_cycles = _positive_int(ctx.config.get("history_cycles"), 2)
    maximum = _positive_int(ctx.config.get("max_observations"), 30)
    feedback_limit = _positive_int(ctx.config.get("feedback_chars"), 300)
    history = _read_json(ctx.run_dir / "feedback" / "evidence" / "history.json")
    prior_ids = (
        [
            str(row.get("genid"))
            for row in history
            if isinstance(row, dict)
            and row.get("genid") is not None
            and re.fullmatch(r"[A-Za-z0-9_.-]+", str(row.get("genid")))
        ]
        if isinstance(history, list)
        else []
    )
    prior_count = max(history_cycles - 1, 0)
    case_paths = [
        ctx.workspace / "runs" / f"gen-{genid}" / "rollout" / "cases.json"
        for genid in (prior_ids[-prior_count:] if prior_count else [])
    ]
    case_paths.append(ctx.run_dir / "rollout" / "cases.json")
    cases: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for path in case_paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        payload = _read_json(path)
        if isinstance(payload, list):
            cases.extend(case for case in payload if isinstance(case, dict))
    return [
        {
            "task_id": case.get("task_name") or case.get("trial_name") or "",
            "success": case.get("outcome") == "passed",
            "score": case.get("reward") if isinstance(case.get("reward"), (int, float)) else 0.0,
            "feedback": _case_feedback(case, feedback_limit),
        }
        for case in cases[-maximum:]
    ]


def _skills(skills_dir: Path) -> list[str]:
    if not skills_dir.is_dir():
        return []
    return sorted(
        path.name
        for path in skills_dir.iterdir()
        if path.is_dir() and not path.name.startswith("_") and (path / "SKILL.md").is_file()
    )


def _drafts(skills_dir: Path) -> list[dict[str, str]]:
    drafts_dir = skills_dir / "_drafts"
    if not drafts_dir.is_dir() or drafts_dir.is_symlink():
        return []
    return [
        {"name": path.stem, "content": path.read_text()[:1000]}
        for path in sorted(drafts_dir.glob("*.md"))
        if path.is_file() and not path.is_symlink()
    ]


def _draft_section(drafts: list[dict[str, str]]) -> str:
    if not drafts:
        return "No draft skills this batch."
    return "\n\n".join(f"#### Draft: {draft['name']}\n```markdown\n{draft['content']}\n```" for draft in drafts)


def _layer_status(config: dict[str, Any], key: str, default: bool) -> str:
    return "enabled" if _enabled(config, key, default) else "disabled"


def _placeholder_rule(config: dict[str, Any], prompt_relative: str) -> str:
    values = config.get("required_placeholders")
    if values is None:
        values = ["{{ instruction }}"] if Path(prompt_relative).name == "prompt.md" else []
    if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
        raise ValueError("required_placeholders must be a list of non-empty strings")
    if not values:
        return ""
    if values == ["{{ instruction }}"]:
        return f"- Preserve the `{{{{ instruction }}}}` placeholder in `{prompt_relative}`."
    rendered = ", ".join(f"`{value}`" for value in values)
    return f"- Preserve these literal template expressions in `{prompt_relative}`: {rendered}."


def _instructions(config: dict[str, Any], template_rule: str, *, trajectory_only: bool = False) -> str:
    instructions = (
        [
            "Analyze the behavior-only trajectory summaries and proxy judge verdicts before editing; do not search "
            "for evaluator labels or test feedback.",
            "Sort tasks by proxy score, prioritize likely failures, and group recurring categories and failure "
            "reasons. Make one coherent, transferable change only when supported by the behavioral evidence.",
        ]
        if trajectory_only
        else [
            "Review the analyze-operator feedback and task summaries before editing; inspect the complete evidence files "
            "when the inline view is truncated or a claim needs verification.",
            "Make one coherent change anywhere inside the mutable surface when supported by the evidence.",
        ]
    )
    if _enabled(config, "evolve_skills", True):
        instructions.append("Review draft skills: refine into a real skill, merge with an existing skill, or discard.")
        instructions.append("Update current skills only when supported by the observations.")
    if _enabled(config, "evolve_prompts", True):
        instructions.append("Update the runtime prompt only with concise, transferable instructions.")
    if _enabled(config, "evolve_memory", True):
        instructions.append("Add or prune long-term memory only when the lesson should apply across tasks.")
    instructions.extend(
        [
            "Do not add standalone files to a disabled context layer unless the same change wires them into runtime.",
            "Inspect files with your filesystem tools before writing.",
            "Verify changes with `git diff` and run proportionate checks.",
        ]
    )
    if template_rule:
        instructions.append(template_rule.removeprefix("- "))
    return "\n".join(f"{index}. {instruction}" for index, instruction in enumerate(instructions, 1))


def _selected_analyze_operator(ctx: OperatorContext) -> str:
    for path in (
        ctx.run_dir / "analyze" / "evidence" / "manifest.json",
        ctx.run_dir / "feedback" / "evidence" / "manifest.json",
    ):
        payload = _read_json(path)
        if isinstance(payload, dict) and payload.get("analyze_operator"):
            return str(payload["analyze_operator"])
    return ""


def _selected_case_count(ctx: OperatorContext) -> int:
    for path in (
        ctx.run_dir / "analyze" / "evidence" / "manifest.json",
        ctx.run_dir / "feedback" / "evidence" / "manifest.json",
    ):
        payload = _read_json(path)
        if isinstance(payload, dict):
            cases = payload.get("cases")
            if isinstance(cases, int) and not isinstance(cases, bool) and cases >= 0:
                return cases
    return 0


def _trajectory_only_evidence(observation: str, ctx: OperatorContext) -> str:
    for path in (
        ctx.run_dir / "feedback" / "evidence" / "selected.md",
        ctx.run_dir / "analyze" / "evidence" / "selected.md",
    ):
        try:
            selected = path.read_text().strip()
        except OSError:
            continue
        if selected:
            break
    else:
        selected = observation.strip() or "(No behavior-only trajectory evidence was produced.)"
    limit = _positive_int(ctx.config.get("evidence_chars"), DEFAULT_INLINE_EVIDENCE_CHARS)
    if len(selected) <= limit:
        return selected
    return selected[:limit] + f"\n...[behavior evidence truncated {len(selected) - limit} chars]..."


def _evidence_section(observation: str, ctx: OperatorContext, *, trajectory_only: bool = False) -> str:
    if trajectory_only:
        return _trajectory_only_evidence(observation, ctx)
    relative_run = Path("runs") / f"gen-{ctx.genid}"
    feedback_root = relative_run / "feedback"
    raw_root = relative_run / "analyze" / "evidence"
    feedback = load_feedback(ctx.run_dir, fallback=observation).strip()
    if not feedback:
        feedback = "(No analyze-operator feedback was produced for this generation.)"
    limit = _positive_int(ctx.config.get("evidence_chars"), DEFAULT_INLINE_EVIDENCE_CHARS)
    marker = f"\n\n[inline evidence truncated; inspect the complete feedback bundle at `{feedback_root.as_posix()}/`]"
    if len(feedback) > limit:
        feedback = feedback[: max(limit - len(marker), 0)] + marker
    return (
        "### Analyze-Operator Feedback\n\n"
        f"{feedback}\n\n"
        f"- Complete feedback bundle: `{feedback_root.as_posix()}/`\n"
        f"- Selected evidence: `{(feedback_root / 'evidence' / 'selected.md').as_posix()}`\n"
        f"- Raw trace evidence: `{raw_root.as_posix()}/`"
    )


def build_prompt(
    checkout: Path,
    ctx: OperatorContext,
    observation: str = "",
) -> tuple[str, dict[str, Any]]:
    prompt_path, prompt_relative = _relative_path(checkout, ctx.config.get("prompt_path"), "target/prompts/system.md")
    if not prompt_path.is_file():
        raise ValueError(f"A-Evolve prompt_path must reference an existing file: {prompt_relative}")
    skills_dir, skills_relative = _relative_path(checkout, ctx.config.get("skills_dir"), "target/skills")
    _, memory_relative = _relative_path(checkout, ctx.config.get("memory_dir"), "target/memory")
    trajectory_only = _selected_analyze_operator(ctx) == TRAJECTORY_ONLY_OPERATOR
    summaries = [] if trajectory_only else _case_summaries(ctx)
    tasks_analyzed = _selected_case_count(ctx) if trajectory_only else len(summaries)
    evolve_skills = _enabled(ctx.config, "evolve_skills", True)
    drafts = _drafts(skills_dir) if evolve_skills else []
    skill_names = _skills(skills_dir)
    template_rule = _placeholder_rule(ctx.config, prompt_relative)
    experiment = Path("/app/task/workspace") if runner_name(ctx) == "harbor" else ctx.workspace
    prompt = (
        f"{AEVOLVE_SYSTEM_PROMPT.rstrip()}\n\n"
        f"## Evolution Cycle #{ctx.genid}\n\n"
        f"### Workspace Layout\n"
        f"- Runtime prompt/config: `{prompt_relative}`\n"
        f"- Reusable skill directories: `{skills_relative}/*/` (required entrypoint: `SKILL.md`)\n"
        f"- Draft skills: `{skills_relative}/_drafts/*.md`\n"
        f"- Memory: `{memory_relative}/`\n\n"
        f"{workspace_contract(checkout, ctx.config)}\n\n"
        "### Managed Evolution Layers\n"
        f"- Prompt evolution: {_layer_status(ctx.config, 'evolve_prompts', True)}\n"
        f"- Skills evolution: {_layer_status(ctx.config, 'evolve_skills', True)}\n"
        f"- Memory evolution: {_layer_status(ctx.config, 'evolve_memory', True)}\n"
        "These switches control which reusable context stores A-Evolve should manage; they are not filesystem permissions.\n\n"
        + (
            f"{_evidence_section(observation, ctx, trajectory_only=True)}\n\n"
            if trajectory_only
            else (
                f"### Task Summaries (last {ctx.config.get('history_cycles', 2)} cycles, at most "
                f"{ctx.config.get('max_observations', 30)})\n```json\n"
                f"{json.dumps(summaries, indent=2, sort_keys=True)}\n```\n\n"
                f"{_evidence_section(observation, ctx)}\n\n"
            )
        )
        + f"### Draft Skills\n{_draft_section(drafts)}\n\n"
        f"### Current Skills ({len(skill_names)})\n"
        f"{chr(10).join(f'- {name}' for name in skill_names) if skill_names else 'No skills yet.'}\n\n"
        f"{render_artifact_guidance(ctx, experiment)}\n\n"
        f"### Instructions\n{_instructions(ctx.config, template_rule, trajectory_only=trajectory_only)}\n\n"
        "Edit the candidate checkout directly. Do not merely print a patch. When done, summarize what you changed and why.\n"
    )
    return prompt, {
        "summaries": summaries,
        "tasks_analyzed": tasks_analyzed,
        "drafts": drafts,
        "skills_before": skill_names,
        "skills_dir": skills_dir,
        "evolve_skills": evolve_skills,
        "trajectory_only": trajectory_only,
    }


def _clear_drafts(skills_dir: Path) -> None:
    drafts_dir = skills_dir / "_drafts"
    if drafts_dir.is_dir() and not drafts_dir.is_symlink():
        for path in drafts_dir.glob("*.md"):
            if path.is_file() and not path.is_symlink():
                path.unlink()


class AEvolveMutate(MutateOperator):
    def mutate(self, checkout: Path, observation: str, ctx: OperatorContext) -> MutateResult:
        parent_ref = patch_parent_ref(checkout, ctx)
        out = ctx.run_dir / "mutate"
        out.mkdir(parents=True, exist_ok=True)
        prompt, state = build_prompt(checkout, ctx, observation)
        if state["trajectory_only"]:
            ctx.config["trajectory_only"] = True
        (out / "prompt.md").write_text(prompt)
        try:
            agent_run = run_agent(checkout, prompt, ctx)
        except AgentCommandError as exc:
            (out / "output.txt").write_text(exc.output)
            _write_json(out / "usage.json", _safe_usage(exc.usage))
            raise SystemExit(exc.returncode)

        if state["evolve_skills"]:
            _clear_drafts(state["skills_dir"])
        skills_before = state["skills_before"]
        skills_after = _skills(state["skills_dir"])
        added = sorted(set(skills_after) - set(skills_before))
        removed = sorted(set(skills_before) - set(skills_after))
        patch = create_candidate_patch(
            checkout=checkout,
            parent_ref=parent_ref,
            surface=load_surface_policy(checkout),
            repair=False,
        )
        usage = _safe_usage(agent_run.usage)
        report = {
            "evo_number": ctx.genid,
            "tasks_analyzed": state["tasks_analyzed"],
            "drafts_reviewed": len(state["drafts"]),
            "skills_before": len(skills_before),
            "skills_after": len(skills_after),
            "new_skills": len(added),
            "skills_added": added,
            "skills_removed": removed,
            "mutated": bool(patch.changed_paths),
            "usage": usage,
        }
        notes = [
            "operator: aevolve",
            f"runner: {runner_name(ctx)}",
            f"tasks-analyzed: {report['tasks_analyzed']}",
            f"drafts-reviewed: {report['drafts_reviewed']}",
            f"new-skills: {report['new_skills']}",
            "written-by: operators/mutate.py",
            *patch.notes,
        ]
        (out / "model_patch.diff").write_text(patch.diff)
        (out / "patch.diff").write_text(patch.diff)
        (out / "output.txt").write_text(agent_run.output)
        (out / "rationale.md").write_text("\n".join(notes) + "\n")
        _write_json(out / "aevolve-report.json", report)
        _write_json(out / "changed.json", patch.changed_paths)
        _write_json(out / "surface-check.json", patch.surface_report)
        _write_json(out / "usage.json", usage)
        return MutateResult(changed=patch.changed_paths, notes=notes, usage=usage)


if __name__ == "__main__":
    sdk.main(AEvolveMutate, validate_config=validate_config)
