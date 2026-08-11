"""Persist a compact GEPA experience and archive pointers to its evidence."""

# ruff: noqa: E402

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evolve.frozen import sdk
from evolve.frozen.config import Config
from evolve.frozen.interfaces import OperatorContext, RecordOperator, RecordResult
from library._shared.gepa import read_json

CONFIG = Config({})


def _relative(path: Path, workspace: Path) -> str | None:
    return path.relative_to(workspace).as_posix() if path.is_file() else None


class GepaRecord(RecordOperator):
    def annotate(self, child: dict[str, Any], ctx: OperatorContext) -> RecordResult:
        proposal_path = ctx.run_dir / "mutate" / "proposal.json"
        comparison_path = ctx.run_dir / "validate" / "comparison.json"
        dataset_path = ctx.run_dir / "analyze" / "evidence" / "reflective_dataset.json"
        proposal = read_json(proposal_path)
        comparison = read_json(comparison_path)
        proposal = proposal if isinstance(proposal, dict) else {}
        comparison = comparison if isinstance(comparison, dict) else {}
        experience = {
            "genid": child.get("genid") or ctx.genid,
            "parent": child.get("parent") or ctx.parent,
            "status": child.get("status"),
            "score": child.get("score"),
            "components": proposal.get("components", []),
            "paths": proposal.get("paths", []),
            "minibatch": {
                key: comparison.get(key)
                for key in ("criterion", "parent_total", "child_total", "delta", "accepted")
                if key in comparison
            },
            "artifacts": {
                "reflective_dataset": _relative(dataset_path, ctx.workspace),
                "proposal": _relative(proposal_path, ctx.workspace),
                "comparison": _relative(comparison_path, ctx.workspace),
            },
        }
        path = ctx.run_dir / "record" / "gepa-experience.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(experience, indent=2, sort_keys=True) + "\n")
        return RecordResult(
            fields={
                "gepa": {
                    "components": experience["components"],
                    "train_score_before": comparison.get("parent_total"),
                    "train_score_after": comparison.get("child_total"),
                    "train_delta": comparison.get("delta"),
                    "accepted_on_train": comparison.get("accepted"),
                    "experience_record": path.relative_to(ctx.workspace).as_posix(),
                }
            }
        )


if __name__ == "__main__":
    sdk.main(GepaRecord, config_schema=CONFIG)
