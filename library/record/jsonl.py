"""JSONL record annotator copies run-dir contract files into archive fields.

It is the default append-only archive recipe for JSON Lines experiment records.
"""

# ruff: noqa: E402

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, RecordOperator, RecordResult, Row


def _record_fields_from_run_dir(run_dir: Path) -> dict[str, Any]:
    gate = json.loads((run_dir / "gate.json").read_text())
    predicted_path = run_dir / "meta_agent" / "predicted_fixes.json"
    predicted_fixes = json.loads(predicted_path.read_text()) if predicted_path.exists() else []
    note = ""
    rationale = run_dir / "meta_agent" / "rationale.md"
    if rationale.exists():
        for line in rationale.read_text().splitlines():
            stripped = line.strip()
            if stripped and stripped != "written-by: operators/meta_agent.py":
                note = stripped
                break
    usage = run_dir / "meta_agent" / "usage.json"
    if usage.exists():
        try:
            usd = json.loads(usage.read_text()).get("usd")
        except Exception:
            usd = None
        if isinstance(usd, (int, float)) and not isinstance(usd, bool) and usd:
            note = f"{note}; usd: {usd}" if note else f"usd: {usd}"
    return {
        "valid_parent": gate["valid_parent"],
        "verdict": gate["verdict"],
        "reason": gate["reason"],
        "predicted_fixes": predicted_fixes,
        "note": note,
    }


class JsonlRecord(RecordOperator):
    def annotate(self, child: Row, ctx: OperatorContext) -> RecordResult:
        return RecordResult(fields=_record_fields_from_run_dir(ctx.run_dir))


if __name__ == "__main__":
    sdk.main(JsonlRecord)
