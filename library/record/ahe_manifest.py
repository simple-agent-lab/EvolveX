"""Compact AHE archive record with verified manifest references."""

# ruff: noqa: E402

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path = [path for path in sys.path if os.path.abspath(path or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]


def _support_dir(script: Path) -> Path:
    resolved = script.resolve()
    for candidate in (resolved.parents[1], resolved.parent.parent / "library"):
        if (candidate / "ahe_support.py").is_file():
            return candidate
    raise ImportError("cannot locate AHE support")


sys.path.insert(0, str(_support_dir(Path(__file__))))

from ahe_support import validate_change_manifest

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, RecordOperator, RecordResult, Row


def _relative_to_workspace(path: Path, workspace: Path) -> str:
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError as error:
        raise ValueError("AHE artifact must be within the workspace") from error


def _task_union(manifest: dict[str, Any], field: str) -> list[str]:
    changes = manifest.get("changes")
    if not isinstance(changes, list):
        raise ValueError("manifest changes must be a list")
    values: set[str] = set()
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get(field), list):
            raise ValueError("manifest %s must be a list" % field)
        if not all(isinstance(task_id, str) and task_id for task_id in change[field]):
            raise ValueError("manifest %s must contain task ids" % field)
        values.update(change[field])
    return sorted(values)


def _attribution_summary(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    attribution = json.loads(path.read_text())
    if not isinstance(attribution, dict):
        raise ValueError("attribution must be an object")
    summary = attribution.get("summary")
    if isinstance(summary, dict) and all(
        isinstance(verdict, str) and isinstance(count, int) and not isinstance(count, bool) and count >= 0
        for verdict, count in summary.items()
    ):
        return dict(sorted(summary.items()))
    changes = attribution.get("changes")
    if not isinstance(changes, list):
        raise ValueError("attribution changes must be a list")
    counts = Counter(
        change["verdict"]
        for change in changes
        if isinstance(change, dict) and isinstance(change.get("verdict"), str)
    )
    return dict(sorted(counts.items()))


def _analysis_paths(run_dir: Path, workspace: Path) -> list[str]:
    analysis = run_dir / "rollout" / "analysis"
    candidates = [
        analysis / "selection.json",
        analysis / "failures.json",
        analysis / "overview.md",
    ]
    detail = analysis / "detail"
    if detail.is_dir():
        candidates.extend(sorted(detail.glob("*.md")))
    return sorted(_relative_to_workspace(path, workspace) for path in candidates if path.is_file())


class AheManifestRecord(RecordOperator):
    def annotate(self, child: Row, ctx: OperatorContext) -> RecordResult:
        gate = json.loads((ctx.run_dir / "gate.json").read_text())
        manifest_path = ctx.run_dir / "meta_agent" / "change_manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        if not isinstance(manifest, dict):
            raise ValueError("change manifest must be an object")
        validate_change_manifest(
            manifest,
            generation=ctx.genid,
            parent=str(ctx.parent),
            changed_paths=list(child.get("mutated") or []),
            run_dir=ctx.run_dir,
            surface_report={"ok": True, "mutated": list(child.get("mutated") or []), "violations": []},
        )
        return RecordResult(
            fields={
                "valid_parent": gate["valid_parent"],
                "verdict": gate["verdict"],
                "reason": gate["reason"],
                "ahe_manifest_path": _relative_to_workspace(manifest_path, ctx.workspace),
                "ahe_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "ahe_decision": manifest["decision"],
                "predicted_fixes": _task_union(manifest, "predicted_fixes"),
                "risk_tasks": _task_union(manifest, "risk_tasks"),
                "ahe_attribution": _attribution_summary(ctx.run_dir / "rollout" / "attribution.json"),
                "ahe_analysis_paths": _analysis_paths(ctx.run_dir, ctx.workspace),
            }
        )


if __name__ == "__main__":
    sdk.main(AheManifestRecord)
