"""The feedback bundle the meta-agent reads — mechanism bookkeeping, not an operator.

Folded out of the retired `observe` operator (DESIGN §7: the canonical verb set
is select/rollout/meta_agent/…/gate/record). The bundle is derived from the ledger +
workspace, so the mechanism owns it: the driver calls `write_feedback_bundle`
after rollout and before meta_agent, and the meta-agent reads
`runs/gen-<id>/feedback/`. It therefore exists even when rollout is a noop
variant, and no operator can suppress it. This is the one home for the logic —
`library/observe/*` is deleted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .archive import archive_path, merged_rows
from .git import git_stdout, tag_exists
from .surface import surface_patterns

Row = dict[str, Any]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _lineage(rows: list[Row]) -> list[Row]:
    return [
        {
            "genid": row.get("genid"),
            "parent": row.get("parent"),
            "score": row.get("score"),
            "status": row.get("status"),
            "valid_parent": row.get("valid_parent"),
        }
        for row in rows
    ]


def _latest_accepted_diff(workspace: Path, rows: list[Row]) -> str:
    for candidate in reversed(rows):
        parent = candidate.get("parent")
        tag = candidate.get("tag")
        if candidate.get("valid_parent") is not True or not parent or not tag:
            continue
        if not (tag_exists(workspace, str(tag)) and tag_exists(workspace, f"gen/{parent}")):
            continue
        diff = git_stdout(workspace, "diff", f"gen/{parent}", str(tag))
        return diff + ("" if not diff or diff.endswith("\n") else "\n")
    return ""


def _surface_rule_lists(workspace: Path) -> tuple[list[str], list[str]]:
    try:
        return surface_patterns(workspace)
    except Exception:
        return ["target/**"], []


def write_feedback_bundle(*, workspace: Path, run_dir: Path, history_k: int = 8) -> list[str]:
    """Write the feedback bundle under run_dir/feedback/ and return its manifest.

    Rows come from the ledger (the bundle is ledger-derived); the driver only
    passes the workspace and the persistent run_dir.
    """
    rows = merged_rows(archive_path(workspace))
    feedback = run_dir / "feedback"
    feedback.mkdir(parents=True, exist_ok=True)
    _write_json(feedback / "lineage.json", _lineage(rows))

    attempts = ["# Attempts", ""]
    attempts += [
        "- gen %s: status=%s score=%s valid_parent=%s reason=%s"
        % (row.get("genid"), row.get("status"), row.get("score"), row.get("valid_parent"), row.get("reason"))
        for row in rows[-int(history_k) :]
    ]
    attempts.append("")
    (feedback / "attempts.md").write_text("\n".join(attempts))

    failures = feedback / "failures"
    failures.mkdir(exist_ok=True)
    (failures / "README.md").write_text("The feedback bundle writes a minimal failure summary.\n")
    (feedback / "last_accepted.diff").write_text(_latest_accepted_diff(workspace, rows))

    prior = [row for row in rows if row.get("predicted_fixes")]
    lines = ["# Falsification", ""]
    lines.extend(
        "- gen %s predicted %s before score %s" % (row.get("genid"), row.get("predicted_fixes"), row.get("score"))
        for row in prior
    )
    if len(lines) == 2:
        lines.append("- No prior predicted fixes recorded.")
    lines.append("")
    (feedback / "falsification.md").write_text("\n".join(lines))

    include, exclude = _surface_rule_lists(workspace)
    (feedback / "rules.md").write_text(
        "# Rules\n\n- Surface include: %s\n- Surface exclude: %s\n- Self-check: `evolve surface-check`\n"
        % (include, exclude)
    )
    (feedback / "index.md").write_text(
        "# Feedback Bundle\n\n"
        "- [lineage](lineage.json)\n"
        "- [attempts](attempts.md)\n"
        "- [failures](failures/)\n"
        "- [last accepted diff](last_accepted.diff)\n"
        "- [falsification](falsification.md)\n"
        "- [rules](rules.md)\n"
    )
    manifest = [
        "feedback/lineage.json",
        "feedback/index.md",
        "feedback/attempts.md",
        "feedback/failures/README.md",
        "feedback/last_accepted.diff",
        "feedback/falsification.md",
        "feedback/rules.md",
    ]
    _write_json(run_dir / "feedback" / "manifest.json", manifest)
    return manifest
