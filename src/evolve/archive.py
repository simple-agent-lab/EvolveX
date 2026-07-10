from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

STAMPED_FIELDS = {"score", "status", "task_set_hash", "task_vector", "evaluation_artifacts", "evaluator_tree", "cost"}
MECHANISM_EVAL_FIELD = "_evolve_mechanism_eval"
RESERVED_AUXILIARY_FIELDS = {"evals", "kind", "round", MECHANISM_EVAL_FIELD}
EVALUATION_FIELDS = STAMPED_FIELDS | {
    "genid",
    "parent",
    "tag",
    "valid_parent",
    "verdict",
    "reason",
    "mutated",
    "surface_violations",
    "predicted_fixes",
    "note",
    "kind",
    "round",
}
AUXILIARY_BLOCKED_FIELDS = (EVALUATION_FIELDS - {"note"}) | {"evals", MECHANISM_EVAL_FIELD}
_SAFE_EXPERIMENT_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def archive_path(workspace: Path) -> Path:
    return workspace / "archive.jsonl"


def mirror_path(experiment_id: str) -> Path:
    evolve_home = Path(os.environ.get("EVOLVE_HOME", Path.home() / ".evolve"))
    return evolve_home / "mirrors" / _safe_experiment_dir(experiment_id) / "archive.jsonl"


def ensure_local_archive(workspace: Path, experiment_id: str) -> None:
    local = archive_path(workspace)
    mirror = mirror_path(experiment_id)
    if not local.exists() and not mirror.exists():
        return
    events: list[str] = []
    seen: set[str] = set()
    for path in (local, mirror):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.strip() or line in seen:
                continue
            events.append(line)
            seen.add(line)
    text = "\n".join(events) + ("\n" if events else "")
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(text)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(text)
    _ensure_receipts(local, mirror)


def append_event(workspace: Path, experiment_id: str, event: dict[str, Any]) -> None:
    line = json.dumps(event, sort_keys=True) + "\n"
    targets = (archive_path(workspace), mirror_path(experiment_id))
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a") as archive:
            archive.write(line)
    if event.get(MECHANISM_EVAL_FIELD) is True:
        for target in targets:
            _append_eval_receipt(target, event)


def read_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def eval_receipt_path(archive: Path) -> Path:
    return archive.with_name(".evolve-eval-receipts.jsonl")


def merged_rows(path: Path) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    evals_by_genid: dict[str, dict[str, dict[str, Any]]] = {}
    top_eval_hash: dict[str, str] = {}
    receipts = _eval_receipts(path)
    order: list[str] = []
    for event in read_events(path):
        genid = str(event["genid"])
        if genid not in rows:
            rows[genid] = {}
            evals_by_genid[genid] = {}
            order.append(genid)
        if _is_keyed_evaluation(event):
            auxiliary_hash = genid in top_eval_hash and str(event["task_set_hash"]) != top_eval_hash[genid]
            if auxiliary_hash and not _has_evaluation_provenance(event, genid, receipts):
                _merge_auxiliary_non_stamped_fields(rows[genid], event)
                continue
            _merge_keyed_evaluation(rows[genid], evals_by_genid[genid], top_eval_hash, genid, event)
            continue
        _merge_event_fields(rows[genid], rows[genid], event)
    return [rows[genid] for genid in order]


def rows_by_genid(workspace: Path) -> dict[str, dict[str, Any]]:
    return {str(row["genid"]): row for row in merged_rows(archive_path(workspace))}


def highest_complete_generation(workspace: Path) -> int:
    highest = -1
    for row in merged_rows(archive_path(workspace)):
        genid = str(row.get("genid", ""))
        if genid.isdigit() and row.get("status") == "complete":
            highest = max(highest, int(genid))
    return highest


def _safe_experiment_dir(experiment_id: str) -> str:
    if _SAFE_EXPERIMENT_ID.fullmatch(experiment_id) and experiment_id not in {".", ".."} and ".." not in experiment_id:
        return experiment_id
    digest = hashlib.sha256(experiment_id.encode("utf-8")).hexdigest()[:16]
    return f"unsafe-{digest}"


def _is_keyed_evaluation(event: dict[str, Any]) -> bool:
    return event.get("task_set_hash") is not None and bool(STAMPED_FIELDS & set(event))


def _has_evaluation_provenance(event: dict[str, Any], genid: str, receipts: set[str]) -> bool:
    return (
        event.get(MECHANISM_EVAL_FIELD) is True
        and _eval_receipt(event) in receipts
        and event.get("tag") == f"gen/{genid}"
        and isinstance(event.get("valid_parent"), bool)
        and event.get("verdict") in {"keep", "discard"}
        and isinstance(event.get("reason"), str)
        and isinstance(event.get("cost"), dict)
    )


def _eval_receipt(event: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()


def _eval_receipts(archive: Path) -> set[str]:
    path = eval_receipt_path(archive)
    return {line.strip() for line in path.read_text().splitlines() if line.strip()} if path.exists() else set()


def verify_integrity(workspace: Path) -> list[str]:
    """Integrity fsck: every frozen mechanism-eval event must have a matching
    tamper-evident receipt. A hand-edited score/status/task_vector changes the
    event's hash, so it no longer matches — surfacing the edit (DESIGN
    observability). Returns human-readable findings; empty means clean."""
    path = archive_path(workspace)
    receipts = _eval_receipts(path)
    findings: list[str] = []
    for event in read_events(path):
        if event.get(MECHANISM_EVAL_FIELD) is True and _eval_receipt(event) not in receipts:
            findings.append(
                f"gen {event.get('genid')} round {event.get('round')}: mechanism-eval "
                "carries no matching receipt — the ledger was hand-edited"
            )
    return findings


def _append_eval_receipt(archive: Path, event: dict[str, Any]) -> None:
    path = eval_receipt_path(archive)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as receipts:
        receipts.write(_eval_receipt(event) + "\n")


def _ensure_receipts(local: Path, mirror: Path) -> None:
    receipts = sorted(_eval_receipts(local) | _eval_receipts(mirror))
    if not receipts:
        return
    for path in (eval_receipt_path(local), eval_receipt_path(mirror)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(receipts) + ("\n" if receipts else ""))


def _merge_keyed_evaluation(
    row: dict[str, Any],
    evals: dict[str, dict[str, Any]],
    top_eval_hash: dict[str, str],
    genid: str,
    event: dict[str, Any],
) -> None:
    task_hash = str(event["task_set_hash"])
    if genid not in top_eval_hash:
        top_eval_hash[genid] = task_hash
        _merge_event_fields(row, row, event)
        return

    if task_hash == top_eval_hash[genid]:
        _merge_event_fields(row, row, event)
        return

    current = evals.get(task_hash)
    if current is None:
        evals[task_hash] = _evaluation_entry(event)
        row["evals"] = list(evals.values())
        _merge_auxiliary_non_stamped_fields(row, event)
        return

    replace_stamped = _can_replace_stamped(current, event)
    for key, value in _evaluation_entry(event).items():
        if key in STAMPED_FIELDS and key in current and not replace_stamped:
            continue
        current[key] = value
    _merge_auxiliary_non_stamped_fields(row, event)
    row["evals"] = list(evals.values())


def _evaluation_entry(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key in EVALUATION_FIELDS}


def _merge_event_fields(row: dict[str, Any], current: dict[str, Any], event: dict[str, Any]) -> None:
    replace_stamped = _can_replace_stamped(current, event)
    for key, value in event.items():
        if key not in RESERVED_AUXILIARY_FIELDS and not (key in STAMPED_FIELDS and key in row and not replace_stamped):
            row[key] = value


def _merge_auxiliary_non_stamped_fields(row: dict[str, Any], event: dict[str, Any]) -> None:
    for key, value in event.items():
        if key not in STAMPED_FIELDS and key not in AUXILIARY_BLOCKED_FIELDS:
            row[key] = value


def _top_eval(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in STAMPED_FIELDS}


def _can_replace_stamped(current: dict[str, Any], event: dict[str, Any]) -> bool:
    if (
        (
            current.get("note") in {"initial scaffold", "mechanism evaluation recorded before gate/record"}
            or current.get("pending_gate_record") is True
        )
        and event.get(MECHANISM_EVAL_FIELD) is True
        and event.get("genid") == current.get("genid")
        and event.get("tag") == current.get("tag")
        and event.get("status") in {"complete", "partial"}
        and event.get("score") is not None
        and event.get("valid_parent") is True
    ):
        return True
    if (
        current.get("pending_gate_record") is True
        and event.get("status") == "operator_failed"
        and event.get("valid_parent") is False
        and event.get("verdict") == "discard"
        and isinstance(event.get("reason"), str)
        and str(event.get("reason")).startswith("operator ")
    ):
        return True
    return (
        current.get("status") == "infra_failed"
        and current.get("score") is None
        and event.get("status") in {"complete", "partial"}
        and event.get("score") is not None
    )
