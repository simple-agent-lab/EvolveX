"""AHE rollout policy for verified MiniSWE trace analysis and attribution."""

# ruff: noqa: E402

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path = [path for path in sys.path if os.path.abspath(path or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]


def _runtime_paths(script: Path) -> tuple[Path, Path]:
    resolved = script.resolve()
    candidates = (
        (resolved.parents[1], resolved.parent / "prompts"),
        (resolved.parent.parent / "library", resolved.parent.parent / "library" / "rollout" / "prompts"),
    )
    for support_dir, prompts_dir in candidates:
        if (support_dir / "ahe_support.py").is_file() and prompts_dir.is_dir():
            return support_dir, prompts_dir
    raise ImportError("cannot locate AHE support and prompt assets")


_SUPPORT_DIR, _PROMPTS = _runtime_paths(Path(__file__))
sys.path.insert(0, str(_SUPPORT_DIR))

from ahe_support import compare_states, evaluate_manifest, select_debugger_tasks, task_states, verify_relative_hash

from evolve.agent import run_meta_agent
from evolve.frozen import sdk
from evolve.frozen.interfaces import ArchiveView, OperatorContext, RolloutOperator, RolloutResult

PROXY_REMOVALS = {
    "http_proxy": None,
    "https_proxy": None,
    "HTTP_PROXY": None,
    "HTTPS_PROXY": None,
    "all_proxy": None,
    "ALL_PROXY": None,
}
_REASON_NAMES = {
    "failure": "failure",
    "regression": "regression",
    "risk": "predicted_risk",
    "control": "successful_control",
}
_SAFE_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_prompt(name: str) -> str:
    return (_PROMPTS / name).read_text()


def _config_dict(config: dict[str, Any], name: str) -> dict[str, Any]:
    value = config.get(name)
    return dict(value) if isinstance(value, dict) else {}


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _nonnegative_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _command(debugger: dict[str, Any]) -> str | None:
    configured = debugger.get("command")
    if configured:
        return str(configured)
    return os.environ.get("EVOLVE_AHE_DEBUGGER_COMMAND") or os.environ.get("EVOLVE_AGENT_COMMAND")


def _manifest(parent: dict[str, Any], workspace: Path) -> dict[str, Any] | None:
    path = parent.get("ahe_manifest_path")
    digest = parent.get("ahe_manifest_sha256")
    if path is None or digest is None:
        return None
    _verified, payload = _verified_bytes(workspace, {"path": path, "sha256": digest})
    loaded = json.loads(payload.decode())
    if not isinstance(loaded, dict):
        raise ValueError("AHE manifest must be an object")
    return loaded


def _verified_bytes(root: Path, reference: object) -> tuple[Path, bytes]:
    verified = verify_relative_hash(root, reference)
    resolved_root = root.resolve()
    resolved = verified.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError("verified artifact escaped its root") from error
    assert isinstance(reference, dict)
    payload = resolved.read_bytes()
    if hashlib.sha256(payload).hexdigest() != reference.get("sha256"):
        raise ValueError("artifact sha256 does not match verified bytes")
    return resolved, payload


def _has_sealed_component(path: Path) -> bool:
    return any(part.casefold() == "sealed" for part in path.parts)


def _resolved_reference_path(root: Path, reference: object) -> Path:
    if not isinstance(reference, dict):
        raise ValueError("artifact reference must be an object")
    relative = reference.get("path")
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("artifact path has an unsafe path")
    path = Path(relative)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("unsafe path")
    resolved_root = root.resolve()
    candidate = (resolved_root / path).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError("unsafe path") from error
    return candidate


def _artifact_index(row: dict[str, Any], workspace: Path) -> dict[str, Any]:
    _verified, payload = _verified_bytes(workspace, row.get("evaluation_artifacts"))
    loaded = json.loads(payload.decode())
    if not isinstance(loaded, dict):
        raise ValueError("evaluation artifact index must be an object")
    return loaded


def _task_artifacts(index: dict[str, Any], task_id: str) -> list[tuple[str, str]]:
    jobs_dir = index.get("jobs_dir")
    if not isinstance(jobs_dir, str) or not jobs_dir:
        raise ValueError("evaluation artifact index jobs_dir must be a path")
    artifact_root = Path(jobs_dir).resolve()
    if not artifact_root.is_dir():
        raise ValueError("evaluation artifact jobs_dir does not exist")
    if _has_sealed_component(artifact_root):
        raise ValueError("sealed artifact jobs_dir is not available to AHE rollout")
    trials = index.get("trials")
    if not isinstance(trials, list):
        raise ValueError("evaluation artifact index trials must be a list")
    evidence: list[tuple[str, str]] = []
    for trial in trials:
        if not isinstance(trial, dict) or str(trial.get("task_name")) != task_id:
            continue
        files = trial.get("files")
        if not isinstance(files, list):
            raise ValueError("evaluation artifact trial files must be a list")
        for reference in files:
            if not isinstance(reference, dict):
                raise ValueError("evaluation artifact file must be an object")
            candidate = _resolved_reference_path(artifact_root, reference)
            if _has_sealed_component(candidate):
                raise ValueError("sealed artifacts are not available to AHE rollout")
            verified, payload = _verified_bytes(artifact_root, reference)
            if _has_sealed_component(verified):
                raise ValueError("sealed artifacts are not available to AHE rollout")
            evidence.append((verified.relative_to(artifact_root).as_posix(), payload.decode()))
    if not evidence:
        raise ValueError(f"no verified training artifacts for task {task_id}")
    return evidence


def _agent_timeouts(vector: object) -> list[str]:
    if not isinstance(vector, dict) or not isinstance(vector.get("tasks"), dict):
        return []
    return sorted(
        str(task_id)
        for task_id, task in vector["tasks"].items()
        if isinstance(task, dict)
        and isinstance(task.get("trials"), list)
        and any(isinstance(trial, dict) and trial.get("status") == "agent_timeout" for trial in task["trials"])
    )


def _selection(
    current_states: dict[str, str], comparison: dict[str, list[str]], predicted_risks: list[str], vector: object, controls: dict[str, Any], generation: int
) -> dict[str, list[str]]:
    selected = select_debugger_tasks(
        current_states,
        comparison,
        predicted_risks,
        successful_controls=_nonnegative_int(controls.get("successful"), 3),
        seed=_nonnegative_int(controls.get("rotation_seed"), 0),
        generation=generation,
    )
    selected["failure"] = sorted(set(selected["failure"]) | set(_agent_timeouts(vector)))
    return selected


def _selection_payload(generation: str, selected: dict[str, list[str]]) -> dict[str, Any]:
    tasks: dict[str, list[str]] = {}
    for category in ("failure", "regression", "risk", "control"):
        for task_id in selected.get(category, []):
            tasks.setdefault(task_id, []).append(_REASON_NAMES[category])
    return {"generation": generation, "tasks": dict(sorted(tasks.items()))}


def _detail_prompt(task_id: str, reasons: list[str], evidence: list[tuple[str, str]]) -> str:
    template = _read_prompt("ahe_debugger.md").rstrip()
    traces = "\n\n".join("## %s\n%s" % (path, text.rstrip()) for path, text in evidence)
    return "%s\n\n# Assigned Task\n%s\n\n# Selection Reasons\n%s\n\n# Verified Training Artifacts\n%s\n" % (
        template,
        task_id,
        ", ".join(reasons),
        traces,
    )


def _report_filename(task_id: str) -> str:
    if _SAFE_TASK_ID.fullmatch(task_id):
        return f"{task_id}.md"
    return f"_task-{hashlib.sha256(task_id.encode()).hexdigest()}.md"


def _overview_prompt(detail_reports: list[Path], attribution: dict[str, Any]) -> str:
    template = _read_prompt("ahe_debugger_overview.md").rstrip()
    reports = "\n\n".join(
        "## %s\n%s" % (report.name, report.read_text().rstrip())
        for report in sorted(detail_reports, key=lambda path: path.name)
    )
    return "%s\n\n# Attribution\n```json\n%s\n```\n\n# Detail Reports\n%s\n" % (
        template,
        json.dumps(attribution, indent=2, sort_keys=True),
        reports,
    )


def _verdict_summary(attribution: dict[str, Any]) -> dict[str, int]:
    changes = attribution.get("changes")
    if not isinstance(changes, list):
        return {"BASELINE": 1}
    verdicts = Counter(
        str(change.get("verdict")) for change in changes if isinstance(change, dict) and isinstance(change.get("verdict"), str)
    )
    return dict(sorted(verdicts.items())) or {"BASELINE": 1}


def _failure_record(task_id: str, attempts: int, error: Exception) -> dict[str, Any]:
    return {"task_id": task_id, "attempts": attempts, "error": str(error)}


class AheTraceAnalysisRollout(RolloutOperator):
    def rollout(self, checkout: Path, ctx: OperatorContext) -> RolloutResult:
        if not ctx.parent:
            raise ValueError("AHE trace analysis requires a selected parent")
        parent = ArchiveView(ctx.workspace).row(ctx.parent)
        if parent is None:
            raise ValueError("selected AHE parent is missing from archive")
        parent_vector = parent.get("task_vector")
        if parent_vector is None:
            raise ValueError("selected AHE parent has no task vector")
        artifact_index = _artifact_index(parent, ctx.workspace)
        parent_manifest = _manifest(parent, ctx.workspace)
        grandparent = ArchiveView(ctx.workspace).row(str(parent["parent"])) if parent.get("parent") is not None else None
        previous_vector = grandparent.get("task_vector") if grandparent else None
        current_states = task_states(parent_vector)
        comparison = compare_states(task_states(previous_vector), current_states) if previous_vector is not None else {
            "improved": [],
            "regressed": [],
            "unchanged": [],
            "unknown": [],
        }
        attribution = evaluate_manifest(parent_manifest, previous_vector, parent_vector) if parent_manifest and previous_vector is not None else {"changes": []}
        attribution["summary"] = _verdict_summary(attribution)

        debugger = _config_dict(ctx.config, "debugger")
        controls = _config_dict(ctx.config, "controls")
        generation = int(ctx.genid) if ctx.genid.isdigit() else 0
        predicted_risks = [
            task_id
            for change in attribution.get("changes", [])
            if isinstance(change, dict)
            for task_id in change.get("risk_tasks", [])
            if isinstance(task_id, str)
        ]
        selection = _selection(current_states, comparison, predicted_risks, parent_vector, controls, generation)
        payload = _selection_payload(ctx.genid, selection)
        analysis_dir = ctx.run_dir / "rollout" / "analysis"
        detail_dir = analysis_dir / "detail"
        scratch_root = analysis_dir / "scratch"
        _write_json(analysis_dir / "selection.json", payload)
        _write_json(ctx.run_dir / "rollout" / "attribution.json", attribution)

        workers = min(5, _positive_int(debugger.get("workers"), 5))
        attempts = _positive_int(debugger.get("attempts"), 1)
        command = _command(debugger)
        timeout_s = debugger.get("timeout_s")
        failures: list[dict[str, Any]] = []
        report_paths = {task_id: detail_dir / _report_filename(task_id) for task_id in payload["tasks"]}
        successful_reports: dict[str, Path] = {}

        def analyze(task_id: str, reasons: list[str]) -> tuple[str, Path | None, dict[str, Any] | None]:
            try:
                scratch_dir = scratch_root / hashlib.sha256(task_id.encode()).hexdigest()
                scratch_dir.mkdir(parents=True, exist_ok=True)
                trajectory_path = scratch_dir / "debugger.trajectory.json"
                task_run_dir = analysis_dir / "task-runs" / hashlib.sha256(task_id.encode()).hexdigest()
                evidence = _task_artifacts(artifact_index, task_id)
                prompt = _detail_prompt(task_id, reasons, evidence)
            except Exception as error:
                return task_id, None, _failure_record(task_id, 0, error)
            last_error: Exception | None = None
            for _attempt in range(1, attempts + 1):
                try:
                    result = run_meta_agent(
                        workspace=scratch_dir,
                        prompt=prompt,
                        config={"command": command, "timeout_s": timeout_s},
                        env_overrides={
                            **PROXY_REMOVALS,
                            "EVOLVE_SOURCE_AGENT_ROLE": "debugger",
                            "EVOLVE_SOURCE_AGENT_OUTPUT_PATH": str(trajectory_path),
                            "EVOLVE_RUN_DIR": str(task_run_dir),
                        },
                    )
                    detail_dir.mkdir(parents=True, exist_ok=True)
                    report_path = report_paths[task_id]
                    report_path.write_text(result.stdout)
                    return task_id, report_path, None
                except Exception as error:  # Record a terminal source-agent failure instead of dropping a diagnosis.
                    last_error = error
            assert last_error is not None
            return task_id, None, _failure_record(task_id, attempts, last_error)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(analyze, task_id, reasons) for task_id, reasons in payload["tasks"].items()]
            for future in as_completed(futures):
                task_id, report_path, failure = future.result()
                if report_path is not None:
                    successful_reports[task_id] = report_path
                if failure is not None:
                    failures.append(failure)

        failure_ids = {str(failure["task_id"]) for failure in failures}
        required = {
            task_id
            for task_id, reasons in payload["tasks"].items()
            if "regression" in reasons or "predicted_risk" in reasons
        }
        for task_id in sorted(required):
            if task_id not in successful_reports and task_id not in failure_ids:
                failures.append({"task_id": task_id, "attempts": 0, "error": "missing required analysis outcome"})
        _write_json(analysis_dir / "failures.json", {"failures": sorted(failures, key=lambda failure: str(failure["task_id"]))})

        overview_scratch = scratch_root / "overview"
        overview_scratch.mkdir(parents=True, exist_ok=True)
        overview = run_meta_agent(
            workspace=overview_scratch,
            prompt=_overview_prompt(list(successful_reports.values()), attribution),
            config={"command": command, "timeout_s": timeout_s},
            env_overrides={
                **PROXY_REMOVALS,
                "EVOLVE_SOURCE_AGENT_ROLE": "debugger_overview",
                "EVOLVE_SOURCE_AGENT_OUTPUT_PATH": str(overview_scratch / "overview.trajectory.json"),
                "EVOLVE_RUN_DIR": str(analysis_dir / "overview-run"),
            },
        )
        (analysis_dir / "overview.md").write_text(overview.stdout)

        artifacts = [
            "rollout/analysis/selection.json",
            *[successful_reports[task_id].relative_to(ctx.run_dir).as_posix() for task_id in sorted(successful_reports)],
            "rollout/analysis/failures.json",
            "rollout/analysis/overview.md",
            "rollout/attribution.json",
        ]
        controls = sum("successful_control" in reasons for reasons in payload["tasks"].values())
        return RolloutResult(
            summary={
                "variant": "ahe_trace_analysis",
                "analyzed": len(payload["tasks"]),
                "failed": len(failures),
                "controls": controls,
                "attribution_verdicts": attribution["summary"],
            },
            artifacts=artifacts,
        )


if __name__ == "__main__":
    sdk.main(AheTraceAnalysisRollout)
