from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from glob import escape
from pathlib import Path
from typing import Any

from .evaluation.datasets import (
    RegistryMetadataClient,
    dataset_content_identity,
    local_task_content_digest,
)

SPLIT_NAMES = ("train", "gate", "sealed")


def build_manifest(
    dataset: str,
    split: dict[str, Any],
    *,
    base_dir: Path,
    sampling: str,
    gate_limit: int,
    registry_client: RegistryMetadataClient | None = None,
) -> dict[str, Any]:
    ratios = _ratios(split)
    seed = _integer(split.get("seed"), "evaluator.split.seed", minimum=0)
    resolved = _resolve_dataset(dataset, base_dir)
    identity = dataset_content_identity(dataset, base_dir=base_dir, client=registry_client)
    names = list(identity.members)
    assignments = _assign(names, ratios, seed)
    empty = [name for name in SPLIT_NAMES if names and ratios[name] > 0 and not assignments[name]]
    if empty:
        raise ValueError(f"evaluator.dataset is too small for non-empty splits: {', '.join(empty)}")
    manifest: dict[str, Any] = {
        "version": 2,
        "dataset": str(resolved) if resolved is not None else dataset,
        "resolved": resolved is not None,
        "identity_status": "verified",
        "seed": seed,
        "ratios": ratios,
        "sampling": sampling,
        "gate_tasks_per_round": max(gate_limit, 0),
        "tasks": assignments,
    }
    manifest["dataset_identity"] = {
        "source": identity.source,
        "digest": identity.digest,
        "resolved_reference": identity.resolved_reference,
    }
    manifest["dataset_digest"] = f"sha256:{identity.digest}"
    manifest["task_digests"] = identity.task_digest_map()
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    return parse_manifest(path.read_text(), source=str(path))


def parse_manifest(text: str, *, source: str = "split manifest") -> dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict) or payload.get("version") not in {1, 2}:
        raise RuntimeError(f"unsupported split manifest: {source}")
    tasks = payload.get("tasks")
    if not isinstance(tasks, dict) or any(not isinstance(tasks.get(name), list) for name in SPLIT_NAMES):
        raise RuntimeError(f"invalid split task lists: {source}")
    if payload["version"] == 1:
        payload.setdefault("identity_status", "legacy_unverified")
        return payload
    identity = payload.get("dataset_identity")
    task_digests = payload.get("task_digests")
    members = [member for split in SPLIT_NAMES for member in tasks[split]]
    identity_source = identity.get("source") if isinstance(identity, dict) else None
    if any(
        not isinstance(member, str)
        or not member
        or member in {".", ".."}
        or "\\" in member
        or (identity_source == "local" and "/" in member)
        or (identity_source == "registry" and any(part in {"", ".", ".."} for part in member.split("/")))
        for member in members
    ) or len(set(members)) != len(members):
        raise RuntimeError(f"verified split manifest must contain disjoint non-empty task names: {source}")
    if (
        payload.get("identity_status") != "verified"
        or not isinstance(identity, dict)
        or identity.get("source") not in {"local", "registry"}
        or not _sha256(identity.get("digest"))
        or not isinstance(identity.get("resolved_reference"), str)
        or not isinstance(task_digests, dict)
        or set(task_digests) != set(members)
        or any(not _sha256(task_digests.get(member)) for member in members)
    ):
        raise RuntimeError(f"invalid content identity in split manifest: {source}")
    return payload


def selected_task_names(
    manifest: dict[str, Any], split_name: str, *, round_number: int | None = None, limit: int | None = None
) -> list[str]:
    if split_name not in SPLIT_NAMES:
        raise RuntimeError(f"unknown evaluator split: {split_name}")
    names = [str(name) for name in manifest["tasks"][split_name]]
    if split_name == "gate":
        configured_limit = _integer(manifest.get("gate_tasks_per_round", 0), "gate_tasks_per_round", minimum=0)
        effective_limit = configured_limit if limit is None else max(limit, 0)
        if manifest.get("sampling") == "per_round" and round_number is not None:
            names.sort(key=lambda name: _digest(f"{manifest.get('seed', 0)}\0{round_number}\0{name}"))
        if effective_limit:
            names = names[:effective_limit]
    elif limit is not None and limit > 0:
        names = names[:limit]
    return names


def split_selection_digest(
    split_name: str,
    names: list[str],
    task_digests: dict[str, str] | None = None,
) -> str:
    del task_digests  # Content identity is certified independently from active membership.
    payload = json.dumps({"split": split_name, "tasks": sorted(names)}, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def harbor_task_pattern(name: str) -> str:
    return escape(name)


def configured_split_selection_digest(
    workspace: Path, split_name: str = "gate", *, round_number: int | None = None
) -> str:
    manifest = load_manifest(workspace / "evaluator" / "splits.json")
    names = selected_task_names(manifest, split_name, round_number=round_number)
    return split_selection_digest(split_name, names)


def select_dataset_tasks(
    manifest_path: Path,
    dataset: str,
    split_name: str,
    *,
    round_number: int | None = None,
    limit: int | None = None,
) -> tuple[list[str], str]:
    manifest = load_manifest(manifest_path)
    identity = manifest.get("dataset_identity")
    source = identity.get("source") if isinstance(identity, dict) else None
    if source == "registry":
        names = selected_task_names(manifest, split_name, round_number=round_number, limit=limit)
        if not names:
            raise RuntimeError(f"evaluator split {split_name!r} contains no tasks")
        return names, split_selection_digest(split_name, names)
    if not manifest.get("resolved"):
        raise RuntimeError(
            "evaluator dataset was not a local task directory during init; "
            "configure evaluator.dataset before init so split membership can be frozen"
        )
    if manifest.get("version") != 2:
        raise RuntimeError(
            "legacy split manifest does not bind task contents; start a new experiment with a v2 split manifest"
        )
    dataset_path = _resolve_dataset(dataset, manifest_path.parent.parent)
    if dataset_path is None:
        raise RuntimeError(f"evaluator dataset is not a local directory: {dataset}")
    expected = sorted(name for split in SPLIT_NAMES for name in manifest["tasks"][split])
    observed = discover_task_names(dataset_path)
    if observed != expected:
        raise RuntimeError(
            "evaluator dataset task names changed after init; start a new experiment with a new split manifest"
        )
    names = selected_task_names(manifest, split_name, round_number=round_number, limit=limit)
    if not names:
        raise RuntimeError(f"evaluator split {split_name!r} contains no tasks")
    if manifest.get("identity_status") == "verified":
        expected_digests = manifest["task_digests"]
        changed = [name for name in names if local_task_content_digest(dataset_path, name) != expected_digests[name]]
        if changed:
            raise RuntimeError("evaluator dataset task contents changed after init: " + ", ".join(changed))
    return names, split_selection_digest(split_name, names)


def write_runtime_selection(
    manifest_path: Path,
    dataset: str,
    split_name: str,
    run_dir: Path,
    *,
    round_number: int | None = None,
    limit: int | None = None,
) -> Path:
    names, digest = select_dataset_tasks(
        manifest_path,
        dataset,
        split_name,
        round_number=round_number,
        limit=limit,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot_selected_tasks(manifest_path, dataset, names, run_dir)
    try:
        _write_runtime_task_selection(run_dir, split_name, names, digest)
    except BaseException:
        shutil.rmtree(snapshot, ignore_errors=True)
        raise
    return snapshot


def write_runtime_task_file_selection(task_file: Path, run_dir: Path, *, limit: int) -> None:
    if limit < 1:
        raise ValueError("task limit must be at least 1")
    names = [
        line.strip()
        for line in task_file.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ][:limit]
    if not names:
        raise RuntimeError("evaluator task file contains no tasks")
    _write_runtime_task_selection(
        run_dir,
        "task_file",
        names,
        split_selection_digest("task_file", names),
    )


def _write_runtime_task_selection(run_dir: Path, split_name: str, names: list[str], digest: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "task-names.txt").write_text("".join(f"{harbor_task_pattern(name)}\n" for name in names))
    (run_dir / "task_set_hash").write_text(f"{digest}\n")
    (run_dir / "task-split.json").write_text(
        json.dumps({"split": split_name, "tasks": names}, indent=2, sort_keys=True) + "\n"
    )


def _snapshot_selected_tasks(
    manifest_path: Path,
    dataset: str,
    names: list[str],
    run_dir: Path,
) -> Path:
    manifest = load_manifest(manifest_path)
    dataset_path = _resolve_dataset(dataset, manifest_path.parent.parent)
    if dataset_path is None:
        raise RuntimeError(f"evaluator dataset is not a local directory: {dataset}")
    sources = (
        {dataset_path.name: dataset_path}
        if (dataset_path / "task.toml").is_file()
        else {path.name: path for path in dataset_path.iterdir() if path.is_dir() and (path / "task.toml").is_file()}
    )
    expected = {name: manifest["task_digests"][name] for name in names}
    snapshot = run_dir / "task-dataset"
    pending = run_dir / ".task-dataset.pending"
    if snapshot.exists() or pending.exists():
        raise RuntimeError(f"evaluator task snapshot already exists: {snapshot}")
    pending.mkdir()
    try:
        for name in names:
            shutil.copytree(sources[name], pending / name, symlinks=True)
        observed = {name: local_task_content_digest(pending, name) for name in names}
        if observed != expected:
            raise RuntimeError("evaluator task snapshot does not match the frozen split content identity")
        pending.replace(snapshot)
    except BaseException:
        shutil.rmtree(pending, ignore_errors=True)
        raise
    return snapshot


def discover_task_names(dataset: Path) -> list[str]:
    if (dataset / "task.toml").is_file():
        return [dataset.name]
    return sorted(path.name for path in dataset.iterdir() if path.is_dir() and (path / "task.toml").is_file())


def task_content_digests(dataset: Path) -> dict[str, str]:
    """Return the certified content digest for every local Harbor task."""

    root = dataset.parent if (dataset / "task.toml").is_file() else dataset
    return {name: local_task_content_digest(root, name) for name in discover_task_names(dataset)}


def _resolve_dataset(dataset: str, base_dir: Path) -> Path | None:
    candidate = Path(dataset).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve() if candidate.is_dir() else None


def _ratios(split: dict[str, Any]) -> dict[str, float]:
    ratios = {name: _number(split.get(name), f"evaluator.split.{name}") for name in SPLIT_NAMES}
    if any(value < 0 for value in ratios.values()):
        raise ValueError("evaluator split ratios must be non-negative")
    if not math.isclose(sum(ratios.values()), 1.0, rel_tol=0, abs_tol=1e-9):
        raise ValueError("evaluator split ratios must sum to 1.0")
    return ratios


def _assign(names: list[str], ratios: dict[str, float], seed: int) -> dict[str, list[str]]:
    ordered = sorted(names, key=lambda name: _digest(f"{seed}\0{name}"))
    raw = {name: len(ordered) * ratios[name] for name in SPLIT_NAMES}
    counts = {name: math.floor(raw[name]) for name in SPLIT_NAMES}
    remainder = len(ordered) - sum(counts.values())
    priority = sorted(SPLIT_NAMES, key=lambda name: (-(raw[name] - counts[name]), SPLIT_NAMES.index(name)))
    for name in priority[:remainder]:
        counts[name] += 1
    result: dict[str, list[str]] = {}
    offset = 0
    for name in SPLIT_NAMES:
        result[name] = sorted(ordered[offset : offset + counts[name]])
        offset += counts[name]
    return result


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _number(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc


def _integer(value: Any, label: str, *, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evolve.splits")
    commands = parser.add_subparsers(dest="command", required=True)
    select = commands.add_parser("select")
    select.add_argument("manifest", type=Path)
    select.add_argument("dataset")
    select.add_argument("split")
    select.add_argument("run_dir", type=Path)
    select.add_argument("round_number", nargs="?", type=int)
    select.add_argument("--limit", type=int)
    task_file = commands.add_parser("limit-file")
    task_file.add_argument("task_file", type=Path)
    task_file.add_argument("run_dir", type=Path)
    task_file.add_argument("--limit", type=int, required=True)
    args = parser.parse_args(argv or sys.argv[1:])
    if args.command == "select":
        write_runtime_selection(
            args.manifest,
            args.dataset,
            args.split,
            args.run_dir,
            round_number=args.round_number,
            limit=args.limit,
        )
    else:
        write_runtime_task_file_selection(args.task_file, args.run_dir, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
