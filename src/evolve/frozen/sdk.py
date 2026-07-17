"""Thin read-only convenience layer over workspace files.

Files remain the source of truth; operators may parse them directly.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, cast

from ..archive import MECHANISM_EVAL_FIELD, STAMPED_FIELDS
from ..git import head_tag, working_tree_changed_paths
from ..surface import check_paths, surface_patterns
from .interfaces import (
    PROTOCOL_VERSION,
    ArchiveView,
    GateOperator,
    MetaAgentOperator,
    NoveltyOperator,
    OperatorContext,
    RecordOperator,
    ReflectOperator,
    RolloutOperator,
    Row,
    SelectOperator,
    TraceAnalyzerOperator,
    ValidateOperator,
    validate_gate_payload,
    validate_meta_agent_payload,
    validate_novelty_payload,
    validate_record_payload,
    validate_reflect_payload,
    validate_rollout_payload,
    validate_select_payload,
    validate_trace_analyzer_payload,
    validate_validate_payload,
)

RECORD_STRIPPED_FIELDS = STAMPED_FIELDS | {
    "genid",
    "parent",
    "tag",
    "mutated",
    "surface_violations",
    "evals",
    "kind",
    "round",
    "pending_gate_record",
    MECHANISM_EVAL_FIELD,
}


def rows(workspace: Path | str = ".") -> list[dict[str, Any]]:
    return ArchiveView(Path(workspace).resolve()).rows()


def row(workspace: Path | str, genid: str) -> dict[str, Any] | None:
    for candidate in rows(workspace):
        if str(candidate.get("genid")) == str(genid):
            return candidate
    return None


def valid_parents(workspace: Path | str = ".") -> list[dict[str, Any]]:
    return ArchiveView(Path(workspace).resolve()).valid_parents()


def best_ever(workspace: Path | str = ".") -> dict[str, Any] | None:
    return ArchiveView(Path(workspace).resolve()).best_ever()


def run_dir(workspace: Path | str, genid: str) -> Path:
    return Path(workspace).resolve() / "runs" / f"gen-{genid}"


def surface_check(workspace: Path | str = ".", parent: str | None = None) -> dict[str, Any]:
    workspace_path = Path(workspace).resolve()
    include, exclude = surface_patterns(workspace_path)
    base = parent or head_tag(workspace_path) or "gen/0"
    mutated = working_tree_changed_paths(workspace_path, base)
    violations = check_paths(mutated, include, exclude)
    return {"ok": not violations, "mutated": mutated, "violations": violations}


def main(operator_cls: type[object]) -> None:
    args = _parse_args()
    config = json.loads(args.config)
    ctx = _context(config)
    _assert_protocol_version(ctx)
    archive = ArchiveView(ctx.workspace)
    operator = operator_cls()

    if issubclass(operator_cls, SelectOperator):
        payload = validate_select_payload(operator.pick(archive, ctx))
        _write_json(ctx.run_dir / "parents.json", payload)
    elif issubclass(operator_cls, RolloutOperator):
        payload = validate_rollout_payload(operator.rollout(ctx.checkout, ctx))
        _write_json(ctx.run_dir / "rollout" / "summary.json", payload["summary"])
        _write_json(ctx.run_dir / "rollout" / "artifacts.json", payload["artifacts"])
    elif issubclass(operator_cls, TraceAnalyzerOperator):
        payload = validate_trace_analyzer_payload(operator.analyze(ctx.checkout, ctx))
        root = ctx.run_dir / "trace_analyzer"
        _write_json(root / "summary.json", payload["summary"])
        _write_json(root / "artifacts.json", payload["artifacts"])
    elif issubclass(operator_cls, MetaAgentOperator):
        payload = validate_meta_agent_payload(operator.run(ctx.checkout, _observation(ctx.run_dir), ctx))
        meta_agent_dir = ctx.run_dir / "meta_agent"
        _write_json(meta_agent_dir / "changed.json", payload["changed"])
        if payload["notes"] and not (meta_agent_dir / "rationale.md").exists():
            (meta_agent_dir / "rationale.md").write_text("\n".join(payload["notes"]) + "\n")
        if not (meta_agent_dir / "usage.json").exists():
            _write_json(meta_agent_dir / "usage.json", payload["usage"])
    elif issubclass(operator_cls, ValidateOperator):
        payload = validate_validate_payload(operator.validate(ctx.checkout, ctx))
        _write_json(ctx.run_dir / "validate" / "result.json", payload)
    elif issubclass(operator_cls, NoveltyOperator):
        payload = validate_novelty_payload(operator.assess(ctx.checkout, ctx))
        _write_json(ctx.run_dir / "novelty.json", payload)
    elif issubclass(operator_cls, GateOperator):
        child, parent = _gate_rows(archive, ctx)
        payload = validate_gate_payload(operator.decide(child, parent, ctx))
        _write_json(ctx.run_dir / "gate.json", _gate_file_payload(payload))
    elif issubclass(operator_cls, RecordOperator):
        payload = validate_record_payload(operator.annotate(_child_row(archive, ctx), ctx))
        fields = {key: value for key, value in payload["fields"].items() if key not in RECORD_STRIPPED_FIELDS}
        _write_json(ctx.run_dir / "record" / "fields.json", fields)
    elif issubclass(operator_cls, ReflectOperator):
        # The playbook is append-only op lines; folding by id (last wins) yields
        # current state. reflect chooses the ops; the mechanism just appends them.
        payload = validate_reflect_payload(operator.reflect(archive, ctx))
        playbook = ctx.workspace / "insights" / "playbook.jsonl"
        playbook.parent.mkdir(parents=True, exist_ok=True)
        with open(playbook, "a") as handle:
            for op in payload["ops"]:
                handle.write(json.dumps(op, ensure_ascii=False) + "\n")
    else:
        raise TypeError("operator_cls must subclass an evolve interface operator")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="{}")
    args, _unknown = parser.parse_known_args()
    return args


def _context(config: dict[str, Any]) -> OperatorContext:
    seed = config.get("seed", 0)
    fan_out = config.get("fan_out", 1)
    return OperatorContext(
        workspace=Path(os.environ["EVOLVE_WORKSPACE"]),
        checkout=Path(os.environ["EVOLVE_CHECKOUT"]),
        run_dir=Path(os.environ["EVOLVE_RUN_DIR"]),
        genid=os.environ["EVOLVE_GENID"],
        parent=os.environ.get("EVOLVE_PARENT") or None,
        round=None,
        fan_out=int(fan_out),
        config=config,
        rng=random.Random(int(seed)),
    )


def _assert_protocol_version(ctx: OperatorContext) -> None:
    marker = ctx.workspace / ".evolve-protocol-version"
    if not marker.exists():
        marker = ctx.checkout / ".evolve-protocol-version"
    if not marker.exists():
        print(f"protocol_version missing: expected {PROTOCOL_VERSION}", file=sys.stderr)
        raise SystemExit(2)
    if marker.read_text().strip() != str(PROTOCOL_VERSION):
        print(f"protocol_version mismatch: expected {PROTOCOL_VERSION}", file=sys.stderr)
        raise SystemExit(2)


def _observation(run_dir: Path) -> str:
    summary_path = run_dir / "rollout" / "summary.json"
    return summary_path.read_text() if summary_path.exists() else ""


def _child_row(archive: ArchiveView, ctx: OperatorContext) -> Row:
    return archive.row(ctx.genid) or {"genid": ctx.genid, "parent": ctx.parent}


def _gate_rows(archive: ArchiveView, ctx: OperatorContext) -> tuple[Row, Row | None]:
    payload = _read_json_if_exists(ctx.run_dir / "gate" / "input.json")
    if isinstance(payload, dict) and isinstance(payload.get("child"), dict):
        data = cast("dict[str, Any]", payload)
        parent = data.get("parent")
        if parent is None or isinstance(parent, dict):
            return dict(data["child"]), dict(parent) if isinstance(parent, dict) else None
    return _child_row(archive, ctx), _parent_row(archive, ctx)


def _parent_row(archive: ArchiveView, ctx: OperatorContext) -> Row | None:
    if ctx.parent is None:
        return None
    parent = archive.row(ctx.parent)
    child = _child_row(archive, ctx)
    task_hash = child.get("task_set_hash")
    if parent is None or task_hash is None:
        return None
    score, matched_from_evals = _score_for_hash(parent, task_hash)
    if score is None:
        return None
    matched = dict(parent)
    matched["score"] = score
    if matched_from_evals:
        matched["_matched_from_evals"] = True
    return matched


def _score_for_hash(row: Row, task_hash: object) -> tuple[object | None, bool]:
    if row.get("task_set_hash") == task_hash:
        return row.get("score"), False
    evals = row.get("evals", []) or []
    for entry in evals:
        if isinstance(entry, dict) and entry.get("task_set_hash") == task_hash:
            return entry.get("score"), True
    return None, False


def _gate_file_payload(payload: dict[str, Any]) -> dict[str, Any]:
    accept = payload["decision"] == "accept"
    return {
        "valid_parent": accept,
        "verdict": "keep" if accept else "discard",
        "reason": payload["reason"],
    }


def _read_json_if_exists(path: Path) -> object | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
