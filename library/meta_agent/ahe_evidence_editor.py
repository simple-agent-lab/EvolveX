"""AHE evidence-driven editor that blocks invalid proposals before evaluation."""

# ruff: noqa: E402

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path = [path for path in sys.path if os.path.abspath(path or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]


def _runtime_paths(script: Path) -> tuple[Path, Path]:
    resolved = script.resolve()
    candidates = (
        (resolved.parents[1], resolved.parent / "prompts"),
        (resolved.parent.parent / "library", resolved.parent.parent / "library" / "meta_agent" / "prompts"),
    )
    for support_dir, prompts_dir in candidates:
        if (support_dir / "ahe_support.py").is_file() and prompts_dir.is_dir():
            return support_dir, prompts_dir
    raise ImportError("cannot locate AHE support and prompt assets")


_SUPPORT_DIR, _PROMPTS = _runtime_paths(Path(__file__))
sys.path.insert(0, str(_SUPPORT_DIR))

from ahe_support import validate_change_manifest

from evolve.agent import AgentCommandError, AgentRunResult, run_meta_agent
from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult, OperatorContext
from evolve.patching import CandidatePatch, SurfacePolicy, create_candidate_patch, load_surface_policy, patch_parent_ref

PROXY_REMOVALS = {
    "http_proxy": None,
    "https_proxy": None,
    "HTTP_PROXY": None,
    "HTTPS_PROXY": None,
    "all_proxy": None,
    "ALL_PROXY": None,
}
_AHE_PROTECTED_PATHS = ("target/harbor_agent.py",)
_SECRET_NAME = re.compile(r"(?:api[_-]?key|token|secret|password|passwd|credential)", re.IGNORECASE)
_TOKEN_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(?:gh[opusr]|github_pat)_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
)
_CREDENTIAL_URL = re.compile(r"\b([A-Za-z][A-Za-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@([^\s]+)")
_SAFE_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_prompt(name: str) -> str:
    return (_PROMPTS / name).read_text()


def _safe_usage(usage: object) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {"usd": 0}
    normalized = dict(usage)
    usd = normalized.get("usd", 0)
    normalized["usd"] = usd if isinstance(usd, (int, float)) and not isinstance(usd, bool) else 0
    return normalized


def _sanitize_text(text: str) -> str:
    secret_values = {
        value
        for name, value in os.environ.items()
        if value and (_SECRET_NAME.search(name) or name in PROXY_REMOVALS)
    }
    for value in sorted(secret_values, key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    text = _CREDENTIAL_URL.sub(r"\1[REDACTED]@\2", text)
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _bounded_int(value: object, default: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 0), maximum)


def _detail_filename(task_id: str) -> str:
    if _SAFE_TASK_ID.fullmatch(task_id):
        return f"{task_id}.md"
    import hashlib

    return f"_task-{hashlib.sha256(task_id.encode()).hexdigest()}.md"


def _selected_detail_reports(run_dir: Path, config: dict[str, Any]) -> str:
    selection_path = run_dir / "rollout" / "analysis" / "selection.json"
    selection = json.loads(selection_path.read_text())
    tasks = selection.get("tasks") if isinstance(selection, dict) else None
    if not isinstance(tasks, dict):
        raise ValueError("AHE selection must contain tasks")
    evidence = config.get("evidence")
    evidence = dict(evidence) if isinstance(evidence, dict) else {}
    max_reports = _bounded_int(evidence.get("max_detail_reports"), 8, 16)
    max_report_chars = _bounded_int(evidence.get("max_report_chars"), 8000, 12000)
    remaining = _bounded_int(evidence.get("max_total_chars"), 32000, 48000)
    detail_dir = (run_dir / "rollout" / "analysis" / "detail").resolve()
    chunks: list[str] = []
    for task_id in sorted(str(task_id) for task_id in tasks)[:max_reports]:
        report = (detail_dir / _detail_filename(task_id)).resolve()
        try:
            report.relative_to(detail_dir)
        except ValueError as error:
            raise ValueError("selected detail report escaped analysis directory") from error
        if not report.is_file() or remaining <= 0:
            continue
        text = _sanitize_text(report.read_text())[:max_report_chars]
        text = text[:remaining]
        remaining -= len(text)
        chunks.append("## %s\n%s" % (task_id, text.rstrip()))
    return "\n\n".join(chunks)


def _rollback_policy(config: dict[str, Any]) -> str:
    rollback = config.get("rollback")
    rollback = dict(rollback) if isinstance(rollback, dict) else {}
    allow_partial = rollback.get("allow_partial") is True
    pivot_after_revert = rollback.get("pivot_after_revert") is True
    partial = "Partial rollback is allowed when evidence separates the reverted files." if allow_partial else "Partial rollback is prohibited; revert the complete harmful change."
    pivot = "A distinct pivot after every revert is required." if pivot_after_revert else "A pivot after revert is optional."
    return f"- {partial}\n- {pivot}"


def _surface_rules(checkout: Path) -> str:
    surface = _ahe_surface(checkout)
    return (
        "- Surface include: %s\n"
        "- Surface exclude: %s\n"
        "- Immutable infrastructure: target/harbor_agent.py, evaluator/, Harbor and Docker configuration, .env, model configuration, and proxy configuration."
    ) % (surface.include, surface.exclude)


def _ahe_surface(checkout: Path) -> SurfacePolicy:
    configured = load_surface_policy(checkout)
    exclude = list(configured.exclude)
    for path in _AHE_PROTECTED_PATHS:
        if path not in exclude:
            exclude.append(path)
    return SurfacePolicy(include=configured.include, exclude=exclude)


def _manifest_path(ctx: OperatorContext) -> Path:
    return ctx.run_dir / "meta_agent" / "change_manifest.json"


def build_ahe_prompt(checkout: Path, ctx: OperatorContext, parent_ref: str | None = None) -> str:
    run_dir = ctx.run_dir
    overview = run_dir / "rollout" / "analysis" / "overview.md"
    attribution = run_dir / "rollout" / "attribution.json"
    attempts = run_dir / "feedback" / "attempts.md"
    manifest_path = _manifest_path(ctx)
    parent_ref = parent_ref or patch_parent_ref(checkout, ctx)
    parent = str(ctx.parent)
    prompt_chunks = [
        _read_prompt("ahe_evolve.md").rstrip(),
        (
            "# Immutable Manifest Identity\n\n"
            "- Generation ID: `%s`\n"
            "- Parent generation ID: `%s`\n"
            "- Parent git ref: `%s`\n\n"
            "Copy exactly `\"generation\": \"%s\"` and `\"parent\": \"%s\"` into `change_manifest.json`."
        )
        % (ctx.genid, parent, parent_ref, ctx.genid, parent),
        "# Experiment Config\n\n```yaml\n%s\n```" % (checkout / "evolve.yaml").read_text().rstrip(),
        "# Analysis Overview\n\n%s" % _sanitize_text(overview.read_text()).rstrip(),
        "# Previous Change Attribution\n\n```json\n%s\n```" % _sanitize_text(attribution.read_text()).rstrip(),
        "# Selected Detail Reports\n\n%s" % _selected_detail_reports(run_dir, ctx.config),
        "# Evolution History\n\n%s" % attempts.read_text().rstrip(),
        "# Rollback Policy\n\n%s" % _rollback_policy(ctx.config),
        "# Surface Rules\n\n%s" % _surface_rules(checkout),
        "# Required Manifest Path\n\n%s" % manifest_path,
    ]
    return "\n\n".join(prompt_chunks) + "\n"


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("AHE change manifest is required")
    try:
        manifest = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError("AHE change manifest is invalid JSON") from error
    if not isinstance(manifest, dict):
        raise ValueError("AHE change manifest must be an object")
    return manifest


def _task_union(manifest: dict[str, Any], field: str) -> list[str]:
    changes = manifest.get("changes")
    if not isinstance(changes, list):
        return []
    return sorted(
        {
            task_id
            for change in changes
            if isinstance(change, dict)
            for task_id in change.get(field, [])
            if isinstance(task_id, str)
        }
    )


def _empty_failure_patch(checkout: Path, parent_ref: str, error: Exception) -> CandidatePatch:
    try:
        return create_candidate_patch(
            checkout=checkout,
            parent_ref=parent_ref,
            surface=_ahe_surface(checkout),
            repair=False,
        )
    except Exception:
        return CandidatePatch(
            changed_paths=[],
            diff="",
            surface_report={"ok": False, "mutated": [], "violations": [], "error": str(error)},
            notes=[],
        )


def _write_result(
    run_dir: Path,
    agent_run: AgentRunResult | None,
    patch: CandidatePatch,
    notes: list[str],
    *,
    manifest: dict[str, Any] | None = None,
    usage: object | None = None,
) -> MetaAgentResult:
    meta_agent_dir = run_dir / "meta_agent"
    meta_agent_dir.mkdir(parents=True, exist_ok=True)
    all_notes = [*notes, *patch.notes, "variant: ahe_evidence_editor"]
    usage_payload = _safe_usage(usage if usage is not None else (agent_run.usage if agent_run else {"usd": 0}))
    _write_json(meta_agent_dir / "changed.json", patch.changed_paths)
    _write_json(meta_agent_dir / "surface-check.json", patch.surface_report)
    (meta_agent_dir / "patch.diff").write_text(patch.diff)
    (meta_agent_dir / "rationale.md").write_text("\n".join(all_notes) + "\n")
    _write_json(meta_agent_dir / "predicted_fixes.json", _task_union(manifest, "predicted_fixes") if manifest else [])
    _write_json(meta_agent_dir / "risk_tasks.json", _task_union(manifest, "risk_tasks") if manifest else [])
    _write_json(meta_agent_dir / "usage.json", usage_payload)
    return MetaAgentResult(changed=patch.changed_paths, notes=all_notes, usage=usage_payload)


def _command(ctx: OperatorContext) -> str | None:
    configured = ctx.config.get("command")
    return str(configured) if configured else os.environ.get("EVOLVE_AGENT_COMMAND")


class AheEvidenceEditor(MetaAgentOperator):
    def run(self, checkout: Path, observation: str, ctx: OperatorContext) -> MetaAgentResult:
        del observation
        parent_ref = patch_parent_ref(checkout, ctx)
        manifest_path = _manifest_path(ctx)
        agent_run: AgentRunResult | None = None
        try:
            command = _command(ctx)
            if not command:
                raise AgentCommandError("missing AHE evolution command; set EVOLVE_AGENT_COMMAND or operators.meta_agent.command", returncode=2)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            agent_run = run_meta_agent(
                workspace=checkout,
                prompt=build_ahe_prompt(checkout, ctx, parent_ref),
                config={"command": command, "timeout_s": ctx.config.get("timeout_s")},
                env_overrides={
                    **PROXY_REMOVALS,
                    "EVOLVE_SOURCE_AGENT_ROLE": "evolution",
                    "EVOLVE_SOURCE_AGENT_OUTPUT_PATH": str(ctx.run_dir / "meta_agent" / "evolution.trajectory.json"),
                    "EVOLVE_AHE_MANIFEST_PATH": str(manifest_path),
                    "EVOLVE_RUN_DIR": str(ctx.run_dir),
                },
            )
            patch = create_candidate_patch(
                checkout=checkout,
                parent_ref=parent_ref,
                surface=_ahe_surface(checkout),
                repair=False,
            )
            if not patch.changed_paths:
                return _write_result(ctx.run_dir, agent_run, patch, ["no source proposal"])
            manifest = _load_manifest(manifest_path)
            validate_change_manifest(
                manifest=manifest,
                generation=ctx.genid,
                parent=str(ctx.parent),
                changed_paths=patch.changed_paths,
                run_dir=ctx.run_dir,
                surface_report=patch.surface_report,
            )
            return _write_result(ctx.run_dir, agent_run, patch, [], manifest=manifest)
        except AgentCommandError as error:
            patch = _empty_failure_patch(checkout, parent_ref, error)
            _write_result(ctx.run_dir, None, patch, ["error: %s" % error], usage=error.usage)
            raise SystemExit(error.returncode)
        except Exception as error:
            patch = _empty_failure_patch(checkout, parent_ref, error)
            _write_result(ctx.run_dir, agent_run, patch, ["error: %s: %s" % (error.__class__.__name__, error)])
            raise SystemExit(str(error))


if __name__ == "__main__":
    sdk.main(AheEvidenceEditor)
