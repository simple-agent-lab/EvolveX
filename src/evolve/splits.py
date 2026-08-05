from __future__ import annotations

import hashlib
import json
import math
import shutil
import stat
import sys
from glob import escape
from pathlib import Path
from typing import Any

SPLIT_NAMES = ("train", "gate", "sealed")


def build_manifest(
    dataset: str,
    split: dict[str, Any],
    *,
    base_dir: Path,
    sampling: str,
    gate_limit: int,
) -> dict[str, Any]:
    ratios = _ratios(split)
    seed = _integer(split.get("seed"), "evaluator.split.seed", minimum=0)
    resolved = _resolve_dataset(dataset, base_dir)
    names = discover_task_names(resolved) if resolved is not None else []
    if resolved is not None and not names:
        raise ValueError(f"evaluator.dataset contains no Harbor task.toml directories: {resolved}")
    task_digests = task_content_digests(resolved) if resolved is not None else {}
    assignments = _assign(names, ratios, seed)
    empty = [name for name in SPLIT_NAMES if names and ratios[name] > 0 and not assignments[name]]
    if empty:
        raise ValueError(f"evaluator.dataset is too small for non-empty splits: {', '.join(empty)}")
    return {
        "version": 2,
        "dataset": str(resolved) if resolved is not None else dataset,
        "resolved": resolved is not None,
        "dataset_digest": _task_digest_map_digest(task_digests) if task_digests else None,
        "task_digests": task_digests,
        "seed": seed,
        "ratios": ratios,
        "sampling": sampling,
        "gate_tasks_per_round": max(gate_limit, 0),
        "tasks": assignments,
    }


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict) or payload.get("version") not in {1, 2}:
        raise RuntimeError(f"unsupported split manifest: {path}")
    tasks = payload.get("tasks")
    if not isinstance(tasks, dict) or any(not isinstance(tasks.get(name), list) for name in SPLIT_NAMES):
        raise RuntimeError(f"invalid split task lists: {path}")
    if payload.get("version") == 2:
        task_digests = payload.get("task_digests")
        if not isinstance(task_digests, dict) or any(
            not isinstance(name, str) or not isinstance(digest, str) for name, digest in task_digests.items()
        ):
            raise RuntimeError(f"invalid task content digests: {path}")
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


def split_selection_digest(split_name: str, names: list[str], task_digests: dict[str, str] | None = None) -> str:
    selected = sorted(names)
    identity: dict[str, Any] = {"split": split_name, "tasks": selected}
    if task_digests:
        missing = [name for name in selected if name not in task_digests]
        if missing:
            raise RuntimeError(f"split manifest has no content digest for tasks: {', '.join(missing)}")
        identity["task_digests"] = {name: task_digests[name] for name in selected}
    payload = json.dumps(identity, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def harbor_task_pattern(name: str) -> str:
    return escape(name)


def configured_split_selection_digest(
    workspace: Path, split_name: str = "gate", *, round_number: int | None = None
) -> str:
    manifest = load_manifest(workspace / "evaluator" / "splits.json")
    names = selected_task_names(manifest, split_name, round_number=round_number)
    return split_selection_digest(split_name, names, _manifest_task_digests(manifest))


def select_dataset_tasks(
    manifest_path: Path,
    dataset: str,
    split_name: str,
    *,
    round_number: int | None = None,
    limit: int | None = None,
) -> tuple[list[str], str]:
    manifest = load_manifest(manifest_path)
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
    frozen_digests = _manifest_task_digests(manifest)
    if manifest.get("version") == 2:
        observed_digests = task_content_digests(dataset_path)
        if observed_digests != frozen_digests:
            raise RuntimeError(
                "evaluator dataset task contents changed after init; start a new experiment with a new split manifest"
            )
    names = selected_task_names(manifest, split_name, round_number=round_number, limit=limit)
    if not names:
        raise RuntimeError(f"evaluator split {split_name!r} contains no tasks")
    return names, split_selection_digest(split_name, names, frozen_digests)


def write_runtime_selection(
    manifest_path: Path,
    dataset: str,
    split_name: str,
    run_dir: Path,
    *,
    round_number: int | None = None,
) -> Path:
    names, digest = select_dataset_tasks(manifest_path, dataset, split_name, round_number=round_number)
    run_dir.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot_selected_tasks(manifest_path, dataset, split_name, names, digest, run_dir)
    try:
        (run_dir / "task-names.txt").write_text("".join(f"{harbor_task_pattern(name)}\n" for name in names))
        (run_dir / "task_set_hash").write_text(f"{digest}\n")
        (run_dir / "task-split.json").write_text(
            json.dumps({"split": split_name, "tasks": names}, indent=2, sort_keys=True) + "\n"
        )
    except BaseException:
        shutil.rmtree(snapshot, ignore_errors=True)
        raise
    return snapshot


def _snapshot_selected_tasks(
    manifest_path: Path,
    dataset: str,
    split_name: str,
    names: list[str],
    selection_digest: str,
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
    frozen = _manifest_task_digests(manifest) or {}
    expected = {name: frozen[name] for name in names}
    snapshot = run_dir / "task-dataset"
    pending = run_dir / ".task-dataset.pending"
    if snapshot.exists() or pending.exists():
        raise RuntimeError(f"evaluator task snapshot already exists: {snapshot}")
    pending.mkdir()
    try:
        for name in names:
            shutil.copytree(sources[name], pending / name, symlinks=True)
        observed = task_content_digests(pending)
        observed_selection = split_selection_digest(split_name, names, observed)
        if observed != expected or observed_selection != selection_digest:
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
    """Return deterministic content identities for every Harbor task in a local dataset."""
    if (dataset / "task.toml").is_file():
        task_paths = {dataset.name: dataset}
    else:
        task_paths = {path.name: path for path in dataset.iterdir() if path.is_dir() and (path / "task.toml").is_file()}
    return {name: _task_tree_digest(task_paths[name]) for name in sorted(task_paths)}


def _task_tree_digest(task_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(task_dir.rglob("*"), key=lambda item: item.relative_to(task_dir).as_posix()):
        relative = path.relative_to(task_dir).as_posix()
        if path.is_symlink():
            raise ValueError(f"evaluator task content may not contain symlinks: {path}")
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir():
            digest.update(f"directory\0{relative}\0{mode:o}\0".encode())
            continue
        if not path.is_file():
            raise ValueError(f"evaluator task content has unsupported file type: {path}")
        data = path.read_bytes()
        digest.update(f"file\0{relative}\0{mode:o}\0".encode())
        digest.update(str(len(data)).encode())
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _task_digest_map_digest(task_digests: dict[str, str]) -> str:
    payload = json.dumps(task_digests, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _manifest_task_digests(manifest: dict[str, Any]) -> dict[str, str] | None:
    task_digests = manifest.get("task_digests")
    if not isinstance(task_digests, dict) or not task_digests:
        return None
    return {str(name): str(digest) for name, digest in task_digests.items()}


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
    args = argv or sys.argv[1:]
    if len(args) not in {5, 6} or args[0] != "select":
        raise SystemExit("usage: python -m evolve.splits select MANIFEST DATASET SPLIT RUN_DIR [ROUND]")
    round_number = int(args[5]) if len(args) == 6 else None
    write_runtime_selection(Path(args[1]), args[2], args[3], Path(args[4]), round_number=round_number)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
