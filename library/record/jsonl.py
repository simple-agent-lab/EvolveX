"""JSONL record annotator copies run-dir contract files into archive fields.

It is the default append-only archive recipe for JSON Lines experiment records.
"""

import json
from pathlib import Path
from typing import Any

from evolve.evaluation.evidence import task_passed
from evolve.frozen import sdk
from evolve.frozen.config import Config
from evolve.frozen.interfaces import ArchiveView, OperatorContext, RecordOperator, RecordResult, Row

CONFIG = Config({})


def _record_fields_from_run_dir(run_dir: Path) -> dict[str, Any]:
    predicted_path = run_dir / "mutate" / "predicted_fixes.json"
    note = ""
    rationale = run_dir / "mutate" / "rationale.md"
    if rationale.exists():
        for line in rationale.read_text().splitlines():
            stripped = line.strip()
            if stripped and stripped != "written-by: operators/mutate.py":
                note = stripped
                break
    usage = run_dir / "mutate" / "usage.json"
    if usage.exists():
        try:
            usd = json.loads(usage.read_text()).get("usd")
        except Exception:
            usd = None
        if isinstance(usd, (int, float)) and not isinstance(usd, bool) and usd:
            note = f"{note}; usd: {usd}" if note else f"usd: {usd}"
    fields = {"note": note} if note else {}
    gate_path = run_dir / "gate.json"
    if gate_path.is_file():
        gate = json.loads(gate_path.read_text())
        fields.update(
            valid_parent=gate["valid_parent"],
            verdict=gate["verdict"],
            reason=gate["reason"],
        )
    if predicted_path.exists():
        fields["predicted_fixes"] = json.loads(predicted_path.read_text())
    return fields


def _verified_fixes(child: Row, ctx: OperatorContext) -> list[str] | None:
    predicted_path = ctx.run_dir / "mutate" / "predicted_fixes.json"
    if not predicted_path.exists():
        return None
    predicted = json.loads(predicted_path.read_text())
    parent = ArchiveView(ctx.workspace).row(str(child.get("parent"))) if child.get("parent") is not None else None
    if parent is None or not predicted or child.get("task_vector") is None or parent.get("task_vector") is None:
        return None
    return [
        task_id
        for task_id in predicted
        if task_passed(parent["task_vector"], task_id) is False and task_passed(child["task_vector"], task_id) is True
    ]


class JsonlRecord(RecordOperator):
    def annotate(self, child: Row, ctx: OperatorContext) -> RecordResult:
        fields = _record_fields_from_run_dir(ctx.run_dir)
        verified = _verified_fixes(child, ctx)
        if verified is not None:
            fields["verified_fixes"] = verified
        return RecordResult(fields=fields)


if __name__ == "__main__":
    sdk.main(JsonlRecord, config_schema=CONFIG)
