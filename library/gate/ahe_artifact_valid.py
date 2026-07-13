"""AHE gate that accepts only structurally valid evaluated artifacts."""

# ruff: noqa: E402

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path = [path for path in sys.path if os.path.abspath(path or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]


def _support_dir(script: Path) -> Path:
    resolved = script.resolve()
    for candidate in (resolved.parents[1], resolved.parent.parent / "library"):
        if (candidate / "ahe_support.py").is_file():
            return candidate
    raise ImportError("cannot locate AHE support")


sys.path.insert(0, str(_support_dir(Path(__file__))))

from ahe_support import validate_change_manifest, verify_relative_hash

from evolve.frozen import sdk
from evolve.frozen.interfaces import GateOperator, GateResult, OperatorContext, Row
from evolve.task_vectors import validate_task_vector


def _reject(artifact: str, error: Exception | str) -> GateResult:
    return GateResult(decision="reject", reason="invalid %s: %s" % (artifact, error))


class AheArtifactValidGate(GateOperator):
    def decide(self, child: Row, parent: Row | None, ctx: OperatorContext) -> GateResult:
        del parent
        if child.get("status") not in {"complete", "partial"}:
            return _reject("status", "not complete or partial")
        score = child.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            return _reject("score", "not numeric")
        try:
            validate_task_vector(child.get("task_vector"))
        except Exception as error:
            return _reject("task_vector", error)
        try:
            verify_relative_hash(ctx.workspace, child.get("artifacts"))
        except Exception as error:
            return _reject("artifacts", error)
        try:
            manifest = json.loads((ctx.run_dir / "meta_agent" / "change_manifest.json").read_text())
            validate_change_manifest(
                manifest,
                generation=ctx.genid,
                parent=str(ctx.parent),
                changed_paths=list(child.get("mutated") or []),
                run_dir=ctx.run_dir,
                surface_report={"ok": True, "mutated": list(child.get("mutated") or []), "violations": []},
            )
        except Exception as error:
            return _reject("change_manifest", error)
        return GateResult(decision="accept", reason="evaluation artifacts and change manifest are valid")


if __name__ == "__main__":
    sdk.main(AheArtifactValidGate)
