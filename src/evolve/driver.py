from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .archive import (
    MECHANISM_EVAL_FIELD,
    STAMPED_FIELDS,
    append_event,
    archive_path,
    ensure_local_archive,
    eval_receipt_path,
    mirror_path,
    read_events,
    rows_by_genid,
)
from .config import evaluator_sampling, experiment_id, operator_blocks
from .evaluator import evaluate
from .frozen import meta_eval
from .frozen.interfaces import (
    PayloadValidationError,
    validate_gate_file_payload,
    validate_meta_agent_predicted_fixes_payload,
    validate_meta_agent_usage_payload,
    validate_novelty_file_payload,
    validate_record_fields_payload,
    validate_rollout_artifacts_payload,
    validate_rollout_summary_payload,
    validate_select_payload,
    validate_validate_file_payload,
)
from .git import (
    add_worktree,
    commit_paths,
    create_tag,
    git,
    git_common_dir,
    git_stdout,
    head_commit,
    remove_worktree,
    tag_exists,
    working_tree_changed_paths,
)
from .operators import OperatorResult, operator_timeout, run_operator
from .population import best_row, format_genid, generation_number, valid_genid, valid_parent_rows
from .surface import check_paths, surface_patterns

DEFAULT_EVAL_REASON = "mechanism evaluation stamp"
PENDING_GATE_RECORD_NOTE = "mechanism evaluation recorded before gate/record"
TERMINAL_STATUSES = {
    "complete",
    "partial",
    "invalid_proposal",
    "no_proposal",
    "operator_failed",
    "rejected_admission",
    "rejected_duplicate",
    "rejected_validation",
}
UNRETRYABLE_STATUSES = TERMINAL_STATUSES - {"complete", "partial"}
RECORD_FORBIDDEN_FIELDS = STAMPED_FIELDS | {
    "genid",
    "parent",
    "tag",
    "mutated",
    "surface_violations",
    "evals",
    "kind",
    "round",
    MECHANISM_EVAL_FIELD,
}


@dataclass(frozen=True)
class RunOptions:
    workspace: Path
    max_generations: int
    children_per_gen: int = 1


@dataclass(frozen=True)
class OperatorOutputError:
    path: Path
    field: str
    detail: str


def run(options: RunOptions) -> None:
    workspace = options.workspace.resolve()
    if options.children_per_gen < 1:
        raise RuntimeError("children_per_gen must be at least 1")
    exp_id = experiment_id(workspace)
    ensure_local_archive(workspace, exp_id)
    operators_config = operator_blocks(workspace)

    for gen in range(1, options.max_generations + 1):
        genids = [
            format_genid(gen, child_index, options.children_per_gen) for child_index in range(options.children_per_gen)
        ]
        rows = rows_by_genid(workspace)
        pending_eval_gate_record = _evaluation_pending_gate_record_genids(workspace)
        pending = [
            genid for genid in genids if _generation_is_pending(rows.get(genid, {}), genid in pending_eval_gate_record)
        ]
        if not pending:
            continue

        round_number = gen if evaluator_sampling(workspace) == "per_round" else None
        selected = _select_generation_parents(
            workspace,
            exp_id,
            gen,
            pending,
            options.children_per_gen,
            operators_config,
        )
        if round_number is not None:
            selected = _ensure_selected_parent_round_evaluations(workspace, exp_id, selected, gen)

        for genid in genids:
            row = rows_by_genid(workspace).get(genid, {})
            pending_eval_gate_record = genid in _evaluation_pending_gate_record_genids(workspace)
            if not _generation_is_pending(row, pending_eval_gate_record):
                continue
            tag = f"gen/{genid}"
            parent = selected.get(genid)
            if parent is None and tag_exists(workspace, tag):
                existing_parent = row.get("parent")
                parent = str(existing_parent) if existing_parent is not None else None
            if parent is None:
                continue
            if tag_exists(workspace, tag):
                _resume_tagged_child(workspace, exp_id, genid, parent, round_number, operators_config)
                continue
            _run_child(workspace, exp_id, genid, parent, round_number, operators_config)


def _run_operator_or_fail(
    *,
    name: str,
    checkout: Path,
    workspace: Path,
    exp_id: str,
    genid: str,
    parent: str,
    run_dir: Path,
    operators_config: dict[str, Any],
    round_number: int | None,
) -> bool:
    """Run one operator guarded; on a crash or malformed output, record the
    failure and return False (the caller discards this generation). Shared by the
    required-operator loop and the optional gates so the failure-handling
    scaffold lives in one place."""
    result = _run_operator_guarded(
        name=name,
        checkout=checkout,
        workspace=workspace,
        exp_id=exp_id,
        genid=genid,
        parent=parent,
        run_dir=run_dir,
        config_block=_operator_config_block(operators_config, name),
        timeout_s=operator_timeout(operators_config, name),
        round_number=round_number,
    )
    if result.returncode != 0:
        _append_operator_failed(workspace, exp_id, genid, parent, name, note=_operator_failure_note(result))
        return False
    error = _operator_output_error(name, run_dir)
    if error is not None:
        _append_operator_failed(workspace, exp_id, genid, parent, name, note=_operator_output_note(error))
        return False
    return True


def _run_child(
    workspace: Path,
    exp_id: str,
    genid: str,
    parent: str,
    round_number: int | None,
    operators_config: dict[str, Any],
) -> None:
    child = _child_worktree_path(workspace, genid)
    if child.exists():
        remove_worktree(workspace, child)
    try:
        try:
            fork_child(workspace, parent, child)
        except Exception as exc:
            _append_operator_failed(
                workspace,
                exp_id,
                genid,
                parent,
                "select",
                note=str(exc),
            )
            return

        for name in ("rollout", "meta_agent"):
            if not _run_operator_or_fail(
                name=name,
                checkout=child,
                workspace=workspace,
                exp_id=exp_id,
                genid=genid,
                parent=parent,
                run_dir=_run_dir(workspace, genid),
                operators_config=operators_config,
                round_number=round_number,
            ):
                return

        mutated_paths = working_tree_changed_paths(child, f"gen/{parent}")
        if not mutated_paths:
            _append_candidate_rejected(
                workspace,
                exp_id,
                genid,
                parent,
                status="no_proposal",
                reason="no changes to commit",
                mutated=[],
            )
            return
        include, exclude = surface_patterns(workspace)
        violations = check_paths(mutated_paths, include, exclude)
        if violations:
            _append_candidate_rejected(
                workspace,
                exp_id,
                genid,
                parent,
                status="invalid_proposal",
                reason="changed paths outside mutable surface",
                mutated=mutated_paths,
                violations=violations,
            )
            return

        if _operator_present(operators_config, "validate"):
            if not _run_operator_or_fail(
                name="validate",
                checkout=child,
                workspace=workspace,
                exp_id=exp_id,
                genid=genid,
                parent=parent,
                run_dir=_run_dir(workspace, genid),
                operators_config=operators_config,
                round_number=round_number,
            ):
                return
            validation, _error = _load_validate_payload(_run_dir(workspace, genid))
            if validation is not None and not validation["accept"]:
                _append_candidate_rejected(
                    workspace,
                    exp_id,
                    genid,
                    parent,
                    status="rejected_validation",
                    reason=f"candidate validation rejected: {validation['reason']}",
                    mutated=mutated_paths,
                )
                return

        # Self-modification admission gate (mechanism 1, DESIGN §2/§7). When a
        # candidate edit touches the operator surface, a confound-free replay
        # decides whether the complete child is non-inferior; rejection discards
        # the target and operator changes together.
        # Skipped inside a replay (recursion guard) and cheap when unchanged.
        if not os.environ.get("EVOLVE_IN_META_EVAL") and meta_eval.operator_surface_changed(mutated_paths):
            verdict = meta_eval.admit(workspace, f"gen/{parent}", child)
            if not verdict.get("admitted"):
                _write_json(_run_dir(workspace, genid) / "meta_eval.json", verdict)
                _append_candidate_rejected(
                    workspace,
                    exp_id,
                    genid,
                    parent,
                    status="rejected_admission",
                    reason="self-modification admission rejected complete child",
                    mutated=mutated_paths,
                )
                return

        # Novelty gate (mechanism 5, DESIGN §7) — optional, off unless the recipe
        # configures `operators.novelty`. Runs on the uncommitted candidate diff;
        # a near-duplicate is discarded before it is ever committed or evaluated.
        if _operator_present(operators_config, "novelty"):
            run_dir = _run_dir(workspace, genid)
            if not _run_operator_or_fail(
                name="novelty",
                checkout=child,
                workspace=workspace,
                exp_id=exp_id,
                genid=genid,
                parent=parent,
                run_dir=run_dir,
                operators_config=operators_config,
                round_number=round_number,
            ):
                return
            nov_payload, _ = _load_novelty_payload(run_dir)
            if nov_payload is not None and not nov_payload["accept"]:
                _append_novelty_rejected(workspace, exp_id, genid, parent, nov_payload)
                return

        commit_child(workspace, child, parent, genid)
    finally:
        if child.exists():
            remove_worktree(workspace, child)

    row = rows_by_genid(workspace).get(genid, {})
    if row.get("status") in {"no_proposal", "invalid_proposal", "operator_failed"}:
        return

    eval_child(workspace, genid, round_number=round_number)
    _run_gate_and_record(workspace, exp_id, genid, parent, operators_config, round_number=round_number)
    verified = _verified_fixes(workspace, genid, parent)
    if verified is not None:
        record_fields(workspace, genid, {"verified_fixes": verified})

    # Reflect (mechanism 2, DESIGN §7) — optional, off unless the recipe configures
    # `operators.reflect`. Reads the ledger (incl. the just-recorded verified_fixes)
    # and appends playbook insights. Best-effort: a reflect failure never unwinds
    # the recorded generation. Runs against the workspace (it needs the ledger,
    # not the candidate worktree).
    if _operator_present(operators_config, "reflect"):
        _run_operator_guarded(
            name="reflect",
            checkout=workspace,
            workspace=workspace,
            exp_id=exp_id,
            genid=genid,
            parent=parent,
            run_dir=_run_dir(workspace, genid),
            config_block=_operator_config_block(operators_config, "reflect"),
            timeout_s=operator_timeout(operators_config, "reflect"),
            round_number=round_number,
        )
    _maybe_quarantine(workspace, genid)


def doctor(workspace: Path) -> list[str]:
    """Detect + repair interrupted state: prune stale child worktrees a crash
    left behind, and report generations pending gate/record that `run` resumes.
    Returns the actions taken/observations (empty means nothing to do)."""
    actions: list[str] = []
    worktrees = workspace / "runs" / "worktrees"
    if worktrees.exists():
        for path in sorted(p for p in worktrees.iterdir() if p.is_dir()):
            remove_worktree(workspace, path)
            actions.append(f"removed stale worktree {path.name}")
    git(workspace, "worktree", "prune", check=False)
    pending = sorted(_evaluation_pending_gate_record_genids(workspace))
    if pending:
        actions.append(f"pending gate/record (run will resume): {', '.join(pending)}")
    return actions


def _maybe_quarantine(workspace: Path, genid: str) -> None:
    """Audit (DESIGN observability): quarantine a suspicious score jump past the
    champion by more than EVOLVE_AUDIT_JUMP (off by default). A `pending` audit
    flags the generation for human review — a huge unexplained gain is often an
    exploit of the ruler, not real progress."""
    margin = os.environ.get("EVOLVE_AUDIT_JUMP")
    if not margin:
        return
    rows = rows_by_genid(workspace)
    child = rows.get(genid, {})
    score = child.get("score")
    prior = [
        float(r["score"])
        for gid, r in rows.items()
        if gid != genid and r.get("valid_parent") is True and isinstance(r.get("score"), (int, float))
    ]
    if isinstance(score, (int, float)) and prior and float(score) - max(prior) > float(margin):
        record_fields(workspace, genid, {"audit": "pending"})


def _verified_fixes(workspace: Path, genid: str, parent: str) -> list[str] | None:
    """Falsification (mechanism 2, DESIGN §2/§7): of the tasks this generation
    predicted it would fix, which ones did its eval actually flip from fail (in
    the parent) to pass? A frozen rule over the two task vectors — not something
    an operator reports. Returns None when it cannot be computed (no task
    vectors / no predictions)."""
    rows = rows_by_genid(workspace)
    child, parent_row = rows.get(genid, {}), rows.get(parent, {})
    child_tv, parent_tv = child.get("task_vector"), parent_row.get("task_vector")
    predicted = child.get("predicted_fixes") or []
    if not isinstance(child_tv, dict) or not isinstance(parent_tv, dict) or not predicted:
        return None
    return [t for t in predicted if child_tv.get(t) is True and parent_tv.get(t) is False]


def _resume_tagged_child(
    workspace: Path,
    exp_id: str,
    genid: str,
    parent: str,
    round_number: int | None,
    operators_config: dict[str, Any],
) -> None:
    row = rows_by_genid(workspace).get(genid, {})
    status = row.get("status")
    needs_gate_record = genid in _evaluation_pending_gate_record_genids(workspace)
    if status not in {"complete", "partial"} or row.get("score") is None:
        eval_child(workspace, genid, round_number=round_number)
        row = rows_by_genid(workspace).get(genid, {})
        status = row.get("status")
        needs_gate_record = genid in _evaluation_pending_gate_record_genids(workspace)
    if needs_gate_record:
        _run_gate_and_record(workspace, exp_id, genid, parent, operators_config, round_number=round_number)


def _run_gate_and_record(
    workspace: Path,
    exp_id: str,
    genid: str,
    parent: str,
    operators_config: dict[str, Any],
    *,
    round_number: int | None = None,
) -> None:
    with tempfile.TemporaryDirectory(prefix=f"evolve-gate-{genid}-") as tempdir:
        checkout = Path(tempdir) / "checkout"
        add_worktree(workspace, checkout, f"gen/{genid}")
        try:
            run_dir = _run_dir(workspace, genid)
            _write_gate_input(workspace, run_dir, genid, parent)
            gate_result = _run_operator_guarded(
                name="gate",
                checkout=checkout,
                workspace=workspace,
                exp_id=exp_id,
                genid=genid,
                parent=parent,
                run_dir=run_dir,
                config_block=_operator_config_block(operators_config, "gate"),
                timeout_s=operator_timeout(operators_config, "gate"),
                round_number=round_number,
            )
            if gate_result.returncode != 0:
                _append_operator_failed(
                    workspace,
                    exp_id,
                    genid,
                    parent,
                    "gate",
                    note=_operator_failure_note(gate_result),
                )
                return
            gate_payload, gate_error = _load_gate_payload(run_dir)
            if gate_error is not None or gate_payload is None:
                _append_operator_failed(
                    workspace,
                    exp_id,
                    genid,
                    parent,
                    "gate",
                    note=_operator_output_note(gate_error),
                )
                return

            record_result = _run_operator_guarded(
                name="record",
                checkout=checkout,
                workspace=workspace,
                exp_id=exp_id,
                genid=genid,
                parent=parent,
                run_dir=run_dir,
                config_block=_operator_config_block(operators_config, "record"),
                timeout_s=operator_timeout(operators_config, "record"),
                round_number=round_number,
            )
            if record_result.returncode != 0:
                _append_operator_failed(
                    workspace,
                    exp_id,
                    genid,
                    parent,
                    "record",
                    note=_operator_failure_note(record_result),
                )
                return
            record_fields_payload, record_error = _load_record_fields(run_dir)
            if record_error is not None or record_fields_payload is None:
                _append_operator_failed(
                    workspace,
                    exp_id,
                    genid,
                    parent,
                    "record",
                    note=_operator_output_note(record_error),
                )
                return
            record_fields(workspace, genid, _strip_record_fields(record_fields_payload))
            if not _row_matches_gate_payload(rows_by_genid(workspace).get(genid, {}), gate_payload):
                _append_operator_failed(
                    workspace,
                    exp_id,
                    genid,
                    parent,
                    "record",
                    note="record/fields.json field valid_parent: record output did not record gate verdict fields",
                )
        finally:
            remove_worktree(workspace, checkout)


def fork_child(workspace: Path, parent: str, child_worktree: Path) -> None:
    workspace = workspace.resolve()
    _assert_valid_parent(workspace, parent)
    if child_worktree.exists():
        if any(child_worktree.iterdir()):
            raise RuntimeError(f"child worktree path is not empty: {child_worktree}")
        child_worktree.rmdir()
    add_worktree(workspace, child_worktree, f"gen/{parent}")


def commit_child(workspace: Path, child_worktree: Path, parent: str, genid: str) -> None:
    workspace = workspace.resolve()
    genid = _validate_genid(genid)
    _assert_valid_parent(workspace, parent)
    if tag_exists(workspace, f"gen/{genid}") or genid in rows_by_genid(workspace):
        raise RuntimeError(f"generation already exists: {genid}")
    _assert_child_worktree_for_parent(workspace, child_worktree, parent)
    exp_id = experiment_id(workspace)
    ensure_local_archive(workspace, exp_id)
    parent_tag = f"gen/{parent}"
    tag = f"gen/{genid}"
    mutated = working_tree_changed_paths(child_worktree, parent_tag)
    if not mutated:
        append_event(
            workspace,
            exp_id,
            {
                "genid": genid,
                "parent": parent,
                "tag": tag,
                "score": None,
                "status": "no_proposal",
                "task_set_hash": None,
                "evaluator_tree": None,
                "valid_parent": False,
                "verdict": "discard",
                "reason": "no changes to commit",
                "mutated": [],
                "surface_violations": [],
                "predicted_fixes": [],
                "note": "no proposal",
                "cost": {"usd": 0, "wall_s": 0},
            },
        )
        return

    include, exclude = surface_patterns(workspace)
    violations = check_paths(mutated, include, exclude)
    if violations:
        _append_candidate_rejected(
            workspace,
            exp_id,
            genid,
            parent,
            status="invalid_proposal",
            reason="changed paths outside mutable surface",
            mutated=mutated,
            violations=violations,
        )
        return

    commit_paths(child_worktree, mutated, f"evolve gen {genid}")
    create_tag(child_worktree, tag)
    append_event(
        workspace,
        exp_id,
        {
            "genid": genid,
            "parent": parent,
            "tag": tag,
            "mutated": mutated,
            "surface_violations": [],
        },
    )


def record_fields(workspace: Path, genid: str, fields: dict[str, object]) -> None:
    workspace = workspace.resolve()
    genid = _validate_genid(genid)
    forbidden = sorted(set(fields) & RECORD_FORBIDDEN_FIELDS)
    if forbidden:
        raise RuntimeError(f"record refuses protected fields: {', '.join(forbidden)}")
    exp_id = experiment_id(workspace)
    ensure_local_archive(workspace, exp_id)
    if genid not in rows_by_genid(workspace):
        raise RuntimeError(f"unknown generation: {genid}")
    append_event(workspace, exp_id, {"genid": genid, **fields})


def eval_child(workspace: Path, genid: str, *, round_number: int | None = None, kind: str = "eval") -> None:
    workspace = workspace.resolve()
    genid = _validate_genid(genid)
    exp_id = experiment_id(workspace)
    ensure_local_archive(workspace, exp_id)
    if round_number is not None and evaluator_sampling(workspace) != "per_round":
        raise RuntimeError("eval --round requires evaluator.sampling: per_round")
    rows = rows_by_genid(workspace)
    row = rows.get(genid, {})
    if round_number is None and row.get("status") in {"complete", "partial"} and row.get("score") is not None:
        return
    if round_number is not None and _row_has_round_evaluation(row, round_number):
        return
    if row.get("status") in UNRETRYABLE_STATUSES:
        return
    parent = str(row.get("parent") or _fallback_parent_for_eval(workspace, rows))
    tag = f"gen/{genid}"
    mutated = row.get("mutated")
    surface_violations = row.get("surface_violations")
    if isinstance(mutated, list) and isinstance(surface_violations, list):
        _stamp_evaluation(
            workspace,
            exp_id,
            genid,
            parent,
            tag,
            [str(path) for path in mutated],
            round_number=round_number,
            kind=kind,
        )
        return
    _finalize_child(workspace, exp_id, genid, parent, tag, round_number=round_number, kind=kind)


def _finalize_child(
    workspace: Path,
    exp_id: str,
    genid: str,
    parent: str,
    tag: str,
    *,
    round_number: int | None = None,
    kind: str = "eval",
) -> None:
    parent_tag = f"gen/{parent}"
    mutated = git_stdout(workspace, "diff", "--name-only", parent_tag, tag).splitlines()
    include, exclude = surface_patterns(workspace)
    violations = check_paths(mutated, include, exclude)
    if violations:
        append_event(
            workspace,
            exp_id,
            {
                "genid": genid,
                "parent": parent,
                "tag": tag,
                "score": None,
                "status": "invalid_proposal",
                "task_set_hash": None,
                "evaluator_tree": None,
                "valid_parent": False,
                "verdict": "discard",
                "reason": "changed paths outside mutable surface",
                "mutated": mutated,
                "surface_violations": violations,
                "predicted_fixes": [],
                "note": "commit rejected by surface",
                "cost": {"usd": 0, "wall_s": 0},
            },
        )
        return
    _stamp_evaluation(workspace, exp_id, genid, parent, tag, mutated, round_number=round_number, kind=kind)


def _stamp_evaluation(
    workspace: Path,
    exp_id: str,
    genid: str,
    parent: str,
    tag: str,
    mutated: list[str],
    *,
    round_number: int | None = None,
    kind: str = "eval",
) -> None:
    result = evaluate(workspace, tag, genid, round_number=round_number)
    valid_parent = result.status in {"complete", "partial"}
    event: dict[str, Any] = {
        "genid": genid,
        "parent": parent,
        "tag": tag,
        "score": result.score,
        "status": result.status,
        "task_set_hash": result.task_set_hash,
        "task_vector": result.task_vector,
        "evaluator_tree": result.evaluator_tree,
        "valid_parent": valid_parent,
        "verdict": "keep" if valid_parent else "discard",
        "reason": DEFAULT_EVAL_REASON,
        "mutated": mutated,
        "surface_violations": [],
        "pending_gate_record": True,
        "predicted_fixes": [],
        "note": PENDING_GATE_RECORD_NOTE,
        "cost": {"usd": 0, "wall_s": result.wall_s},
    }
    if round_number is not None:
        event["kind"] = kind
        event["round"] = round_number
        event[MECHANISM_EVAL_FIELD] = True
    append_event(workspace, exp_id, event)


def _ensure_selected_parent_round_evaluations(
    workspace: Path,
    exp_id: str,
    selected: dict[str, str],
    generation: int,
) -> dict[str, str]:
    usable = dict(selected)
    for parent in sorted(set(selected.values())):
        try:
            _assert_valid_parent(workspace, parent)
        except Exception as exc:
            for genid, selected_parent in selected.items():
                if selected_parent != parent:
                    continue
                _append_operator_failed(
                    workspace,
                    exp_id,
                    genid,
                    parent,
                    "select",
                    note=str(exc),
                )
                usable.pop(genid, None)
            continue
        _ensure_parent_round_evaluation(workspace, exp_id, parent, generation)
    return usable


def _ensure_parent_round_evaluation(workspace: Path, exp_id: str, parent: str, generation: int) -> None:
    row = rows_by_genid(workspace).get(parent, {})
    if _row_has_round_evaluation(row, generation):
        return
    result = evaluate(
        workspace,
        f"gen/{parent}",
        parent,
        round_number=generation,
        run_name=f"eval-round-{generation}",
    )
    valid_parent = result.status in {"complete", "partial"}
    append_event(
        workspace,
        exp_id,
        {
            "genid": parent,
            "parent": row.get("parent"),
            "tag": f"gen/{parent}",
            "score": result.score,
            "status": result.status,
            "task_set_hash": result.task_set_hash,
            "evaluator_tree": result.evaluator_tree,
            "valid_parent": valid_parent,
            "verdict": "keep" if valid_parent else "discard",
            "reason": "mechanism re-evaluation stamp",
            "mutated": row.get("mutated", []),
            "surface_violations": row.get("surface_violations", []),
            "predicted_fixes": row.get("predicted_fixes", []),
            "note": "parent baseline for per-round task set",
            "cost": {"usd": 0, "wall_s": result.wall_s},
            "kind": "reeval",
            "round": generation,
            MECHANISM_EVAL_FIELD: True,
        },
    )
    if not valid_parent:
        raise RuntimeError(f"parent baseline for gen/{parent} round {generation} produced {result.status}")


def _row_has_round_evaluation(row: dict[str, Any], round_number: int) -> bool:
    if row.get("round") == round_number and _is_scored_evaluation(row):
        return True
    return any(
        isinstance(entry, dict) and entry.get("round") == round_number and _is_scored_evaluation(entry)
        for entry in row.get("evals", [])
    )


def _is_scored_evaluation(event: dict[str, Any]) -> bool:
    return (
        event.get("status") in {"complete", "partial"}
        and event.get("score") is not None
        and event.get("task_set_hash") is not None
    )


def _select_generation_parents(
    workspace: Path,
    exp_id: str,
    generation: int,
    pending_genids: list[str],
    children_per_gen: int,
    operators_config: dict[str, Any],
) -> dict[str, str]:
    candidates = valid_parent_rows(workspace) if evaluator_sampling(workspace) == "per_round" else []
    selector = max(
        candidates, key=lambda row: (generation_number(str(row["genid"])) or -1, str(row["genid"])), default=None
    )
    best = selector if selector is not None else best_row(workspace)
    select_tag = str(best.get("tag")) if best else "gen/0"
    run_dir = workspace / "runs" / f"gen-{generation}" / "select"
    with tempfile.TemporaryDirectory(prefix=f"evolve-select-{generation}-") as tempdir:
        checkout = Path(tempdir) / "checkout"
        add_worktree(workspace, checkout, select_tag)
        try:
            result = _run_operator_guarded(
                name="select",
                checkout=checkout,
                workspace=workspace,
                exp_id=exp_id,
                genid=str(generation),
                parent=None,
                run_dir=run_dir,
                config_block=_operator_config_block(operators_config, "select"),
                timeout_s=operator_timeout(operators_config, "select"),
                round_number=generation if evaluator_sampling(workspace) == "per_round" else None,
            )
        finally:
            remove_worktree(workspace, checkout)

    if result.returncode != 0:
        for genid in pending_genids:
            _append_operator_failed(
                workspace,
                exp_id,
                genid,
                None,
                "select",
                note=_operator_failure_note(result),
            )
        return {}

    parents, parents_error = _load_parents(run_dir)
    if parents_error is not None or not parents:
        for genid in pending_genids:
            _append_operator_failed(
                workspace,
                exp_id,
                genid,
                None,
                "select",
                note=_operator_output_note(parents_error),
            )
        return {}

    selected: dict[str, str] = {}
    for child_index, genid in enumerate(
        format_genid(generation, index, children_per_gen) for index in range(children_per_gen)
    ):
        if genid not in pending_genids:
            continue
        if len(parents) == 1:
            selected[genid] = parents[0]
            continue
        if child_index < len(parents):
            selected[genid] = parents[child_index]
            continue
        _append_operator_failed(
            workspace,
            exp_id,
            genid,
            None,
            "select",
            note="parents.json missing child slot",
        )
    return selected


def _load_parents(run_dir: Path) -> tuple[list[str] | None, OperatorOutputError | None]:
    payload, error = _load_validated_json(
        run_dir,
        Path("parents.json"),
        "parents",
        validate_select_payload,
    )
    if error is not None or payload is None:
        return None, error
    return list(payload["parents"]), None


def _evaluation_pending_gate_record_genids(workspace: Path) -> set[str]:
    pending: set[str] = set()
    for event in read_events(archive_path(workspace)):
        genid = str(event.get("genid", ""))
        if _event_is_evaluation_stamp(event):
            pending.add(genid)
            continue
        if genid in pending and _event_is_gate_record_event(event):
            pending.discard(genid)
    return pending


def _event_is_evaluation_stamp(event: dict[str, Any]) -> bool:
    status = event.get("status")
    return (
        status == "infra_failed" or (status in {"complete", "partial"} and event.get("score") is not None)
    ) and _event_marks_pending_gate_record(event)


def _event_marks_pending_gate_record(event: dict[str, Any]) -> bool:
    return event.get("pending_gate_record") is True or event.get("note") == PENDING_GATE_RECORD_NOTE


def _event_is_gate_record_event(event: dict[str, Any]) -> bool:
    return STAMPED_FIELDS.isdisjoint(event) and {"valid_parent", "verdict", "reason"} <= set(event)


def _generation_is_pending(row: dict[str, Any], needs_gate_record: bool) -> bool:
    status = row.get("status")
    return status not in TERMINAL_STATUSES or needs_gate_record


def _load_gate_payload(run_dir: Path) -> tuple[dict[str, Any] | None, OperatorOutputError | None]:
    return _load_validated_json(run_dir, Path("gate.json"), "valid_parent", validate_gate_file_payload)


def _load_novelty_payload(run_dir: Path) -> tuple[dict[str, Any] | None, OperatorOutputError | None]:
    return _load_validated_json(run_dir, Path("novelty.json"), "accept", validate_novelty_file_payload)


def _load_validate_payload(run_dir: Path) -> tuple[dict[str, Any] | None, OperatorOutputError | None]:
    return _load_validated_json(
        run_dir,
        Path("validate") / "result.json",
        "accept",
        validate_validate_file_payload,
    )


def _load_record_fields(run_dir: Path) -> tuple[dict[str, Any] | None, OperatorOutputError | None]:
    return _load_validated_json(run_dir, Path("record") / "fields.json", "fields", validate_record_fields_payload)


def _write_gate_input(workspace: Path, run_dir: Path, genid: str, parent: str) -> None:
    rows = rows_by_genid(workspace)
    child = dict(rows.get(genid) or {"genid": genid, "parent": parent})
    parent_row = _matched_gate_parent(rows.get(parent), child)
    _write_json(run_dir / "gate" / "input.json", {"child": child, "parent": parent_row})


def _matched_gate_parent(parent: dict[str, Any] | None, child: dict[str, Any]) -> dict[str, Any] | None:
    task_hash = child.get("task_set_hash")
    if parent is None or task_hash is None:
        return None
    source = parent if parent.get("task_set_hash") == task_hash else None
    if source is None:
        evals = parent.get("evals", []) or []
        source = next(
            (entry for entry in evals if isinstance(entry, dict) and entry.get("task_set_hash") == task_hash), None
        )
    if source is None or source.get("score") is None:
        return None
    matched = dict(parent)
    matched["score"] = source["score"]
    if source is not parent:
        matched["_matched_from_evals"] = True
    return matched


def _operator_output_error(name: str, run_dir: Path) -> OperatorOutputError | None:
    checks: tuple[tuple[Path, str, Callable[[object], object]], ...]
    if name == "rollout":
        checks = (
            (Path("rollout") / "summary.json", "summary", validate_rollout_summary_payload),
            (Path("rollout") / "artifacts.json", "artifacts", validate_rollout_artifacts_payload),
        )
    elif name == "meta_agent":
        checks = (
            (
                Path("meta_agent") / "predicted_fixes.json",
                "predicted_fixes",
                validate_meta_agent_predicted_fixes_payload,
            ),
            (Path("meta_agent") / "usage.json", "usage", validate_meta_agent_usage_payload),
        )
    elif name == "validate":
        checks = ((Path("validate") / "result.json", "accept", validate_validate_file_payload),)
    elif name == "novelty":
        checks = ((Path("novelty.json"), "accept", validate_novelty_file_payload),)
    else:
        return None
    for relative_path, field, validator in checks:
        _payload, error = _load_validated_json(run_dir, relative_path, field, validator)
        if error is not None:
            return error
    return None


def _load_validated_json(
    run_dir: Path,
    relative_path: Path,
    field: str,
    validator: Callable[[Any], Any],
) -> tuple[Any | None, OperatorOutputError | None]:
    path = run_dir / relative_path
    if not path.exists():
        return None, OperatorOutputError(relative_path, field, "missing file")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return None, OperatorOutputError(relative_path, field, f"invalid json: {exc.msg}")
    try:
        return validator(payload), None
    except PayloadValidationError as exc:
        return None, OperatorOutputError(relative_path, exc.field, str(exc))
    except ValueError as exc:
        return None, OperatorOutputError(relative_path, field, str(exc))


def _append_operator_failed(
    workspace: Path,
    exp_id: str,
    genid: str,
    parent: str | None,
    operator_name: str,
    note: str,
) -> None:
    append_event(
        workspace,
        exp_id,
        {
            "genid": genid,
            "parent": parent,
            "tag": f"gen/{genid}",
            "score": None,
            "status": "operator_failed",
            "task_set_hash": None,
            "evaluator_tree": None,
            "valid_parent": False,
            "verdict": "discard",
            "reason": f"operator {operator_name} failed",
            "mutated": [],
            "surface_violations": [],
            "predicted_fixes": [],
            "note": note,
            "cost": {"usd": 0, "wall_s": 0},
        },
    )


def _append_candidate_rejected(
    workspace: Path,
    exp_id: str,
    genid: str,
    parent: str,
    *,
    status: str,
    reason: str,
    mutated: list[str],
    violations: list[str] | None = None,
) -> None:
    append_event(
        workspace,
        exp_id,
        {
            "genid": genid,
            "parent": parent,
            "tag": f"gen/{genid}",
            "score": None,
            "status": status,
            "task_set_hash": None,
            "evaluator_tree": None,
            "valid_parent": False,
            "verdict": "discard",
            "reason": reason,
            "mutated": mutated,
            "surface_violations": list(violations or []),
            "predicted_fixes": [],
            "note": reason,
            "cost": {"usd": 0, "wall_s": 0},
        },
    )


def _append_novelty_rejected(
    workspace: Path, exp_id: str, genid: str, parent: str | None, payload: dict[str, Any]
) -> None:
    """Record a candidate edit rejected by the novelty gate — discarded, not evaluated,
    and never committed (mechanism 5, DESIGN §7)."""
    append_event(
        workspace,
        exp_id,
        {
            "genid": genid,
            "parent": parent,
            "tag": f"gen/{genid}",
            "score": None,
            "status": "rejected_duplicate",
            "task_set_hash": None,
            "evaluator_tree": None,
            "valid_parent": False,
            "verdict": "discard",
            "reason": "novelty gate rejected a near-duplicate candidate edit",
            "mutated": [],
            "surface_violations": [],
            "predicted_fixes": [],
            "novelty": payload.get("novelty"),
            "note": f"novelty={payload.get('novelty')}",
            "cost": {"usd": 0, "wall_s": 0},
        },
    )


def _operator_output_note(error: OperatorOutputError | None) -> str:
    if error is None:
        return "operator output missing or malformed"
    return f"{error.path.as_posix()} field {error.field}: {error.detail}"


def _strip_record_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if key not in RECORD_FORBIDDEN_FIELDS}


def _gate_fallback_fields(
    *,
    gate_payload: dict[str, Any] | None,
    default_reason: str,
    note: str | None = None,
) -> dict[str, object]:
    fields: dict[str, object] = {
        "valid_parent": False,
        "verdict": "discard",
        "reason": default_reason,
    }
    if gate_payload is not None:
        fields["valid_parent"] = gate_payload["valid_parent"]
        fields["verdict"] = gate_payload["verdict"]
        fields["reason"] = gate_payload["reason"]
    if note:
        fields["note"] = note
    return fields


def _operator_config_block(operators_config: dict[str, Any], name: str) -> dict[str, Any]:
    block = operators_config.get(name)
    return block if isinstance(block, dict) else {}


def _operator_present(operators_config: dict[str, Any], name: str) -> bool:
    """An optional operator is enabled when its key is present — even as `{}`
    (an empty config block is still an opt-in, not `off`)."""
    return isinstance(operators_config.get(name), dict)


def _run_operator_guarded(
    *,
    name: str,
    checkout: Path,
    workspace: Path,
    exp_id: str,
    genid: str,
    parent: str | None,
    run_dir: Path,
    config_block: dict[str, Any],
    timeout_s: float,
    allow_record: bool = False,
    round_number: int | None = None,
) -> OperatorResult:
    before = _archive_line_snapshots(workspace, exp_id)
    if checkout.resolve() != workspace.resolve():
        _write_archive_lines(archive_path(checkout), before[archive_path(workspace)])
        receipts = _archive_lines(eval_receipt_path(archive_path(workspace)))
        if receipts:
            _write_archive_lines(eval_receipt_path(archive_path(checkout)), receipts)
    result = run_operator(
        name=name,
        checkout=checkout,
        workspace=workspace,
        genid=genid,
        parent=parent,
        run_dir=run_dir,
        config_block=config_block,
        timeout_s=timeout_s,
        round_number=round_number,
    )
    if allow_record and checkout.resolve() != workspace.resolve():
        kept = [
            line
            for line in _archive_lines(archive_path(checkout))[len(before[archive_path(workspace)]) :]
            if _allowed_record_line(line, genid)
        ]
        before = {path: lines + kept for path, lines in before.items()}
    _restore_operator_archive_writes(before, genid, allow_record)
    return result


def _archive_line_snapshots(workspace: Path, exp_id: str) -> dict[Path, list[str]]:
    return {path: _archive_lines(path) for path in (archive_path(workspace), mirror_path(exp_id))}


def _archive_lines(path: Path) -> list[str]:
    return path.read_text().splitlines() if path.exists() else []


def _restore_operator_archive_writes(before: dict[Path, list[str]], genid: str, allow_record: bool) -> None:
    for path, original in before.items():
        current = _archive_lines(path)
        appended = current[len(original) :] if current[: len(original)] == original else []
        kept = [line for line in appended if allow_record and _allowed_record_line(line, genid)]
        _write_archive_lines(path, original + kept)


def _write_archive_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _allowed_record_line(line: str, genid: str) -> bool:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return False
    if str(event.get("genid")) != genid:
        return False
    return not ((set(event) - {"genid"}) & RECORD_FORBIDDEN_FIELDS)


def _run_dir(workspace: Path, genid: str) -> Path:
    return workspace / "runs" / f"gen-{genid}"


def _operator_failure_note(result: OperatorResult) -> str:
    return (
        _tail_text(result.stderr) or _tail_text(result.stdout) or f"operator {result.name} exited {result.returncode}"
    )


def _tail_text(text: str, limit: int = 240) -> str:
    stripped = text.strip()
    return "" if not stripped else stripped if len(stripped) <= limit else stripped[-limit:]


def _row_matches_gate_payload(row: dict[str, object], gate_payload: dict[str, Any]) -> bool:
    return (
        row.get("valid_parent") == gate_payload["valid_parent"]
        and row.get("verdict") == gate_payload["verdict"]
        and row.get("reason") == gate_payload["reason"]
    )


def _child_worktree_path(workspace: Path, genid: str) -> Path:
    return workspace / "runs" / "worktrees" / f"gen-{genid}"


def _fallback_parent_for_eval(
    workspace: Path,
    rows: dict[str, dict[str, object]],
    max_generation: int | None = None,
) -> str:
    filtered_rows = []
    for genid, row in rows.items():
        generation = generation_number(genid)
        if generation is None:
            continue
        if max_generation is not None and generation > max_generation:
            continue
        filtered_rows.append(row)
    best = best_row(workspace, filtered_rows)
    if best is None:
        raise RuntimeError("no valid parent available")
    return str(best["genid"])


def _validate_genid(genid: str) -> str:
    if not valid_genid(genid):
        raise RuntimeError(f"generation id must be numeric: {genid}")
    return genid


def _assert_valid_parent(workspace: Path, parent: str) -> None:
    parent = _validate_genid(parent)
    ensure_local_archive(workspace, experiment_id(workspace))
    rows = rows_by_genid(workspace)
    row = rows.get(parent)
    if row is None:
        raise RuntimeError(f"unknown parent: {parent}")
    if row.get("valid_parent") is not True or row.get("status") not in {"complete", "partial"}:
        raise RuntimeError(f"parent gen/{parent} is not a valid parent")
    if not tag_exists(workspace, f"gen/{parent}"):
        raise RuntimeError(f"missing tag for parent gen/{parent}")


def _assert_child_worktree_for_parent(workspace: Path, child_worktree: Path, parent: str) -> None:
    if git_common_dir(workspace) != git_common_dir(child_worktree):
        raise RuntimeError("child worktree does not belong to the workspace repository")
    parent_head = git_stdout(workspace, "rev-parse", f"gen/{parent}^{{commit}}")
    if head_commit(child_worktree) != parent_head:
        raise RuntimeError(f"child worktree is not based on gen/{parent}")
