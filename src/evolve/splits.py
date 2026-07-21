from __future__ import annotations

import hashlib
import json
import math
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
    assignments = _assign(names, ratios, seed)
    empty = [name for name in SPLIT_NAMES if names and ratios[name] > 0 and not assignments[name]]
    if empty:
        raise ValueError(f"evaluator.dataset is too small for non-empty splits: {', '.join(empty)}")
    return {
        "version": 1,
        "dataset": str(resolved) if resolved is not None else dataset,
        "resolved": resolved is not None,
        "seed": seed,
        "ratios": ratios,
        "sampling": sampling,
        "gate_tasks_per_round": max(gate_limit, 0),
        "tasks": assignments,
    }


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise RuntimeError(f"unsupported split manifest: {path}")
    tasks = payload.get("tasks")
    if not isinstance(tasks, dict) or any(not isinstance(tasks.get(name), list) for name in SPLIT_NAMES):
        raise RuntimeError(f"invalid split task lists: {path}")
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


def split_selection_digest(split_name: str, names: list[str]) -> str:
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
    if not manifest.get("resolved"):
        raise RuntimeError(
            "evaluator dataset was not a local task directory during init; "
            "configure evaluator.dataset before init so split membership can be frozen"
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
    return names, split_selection_digest(split_name, names)


def write_runtime_selection(
    manifest_path: Path,
    dataset: str,
    split_name: str,
    run_dir: Path,
    *,
    round_number: int | None = None,
) -> None:
    names, digest = select_dataset_tasks(manifest_path, dataset, split_name, round_number=round_number)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "task-names.txt").write_text("".join(f"{harbor_task_pattern(name)}\n" for name in names))
    (run_dir / "task_set_hash").write_text(f"{digest}\n")
    (run_dir / "task-split.json").write_text(
        json.dumps({"split": split_name, "tasks": names}, indent=2, sort_keys=True) + "\n"
    )


def discover_task_names(dataset: Path) -> list[str]:
    if (dataset / "task.toml").is_file():
        return [dataset.name]
    return sorted(path.name for path in dataset.iterdir() if path.is_dir() and (path / "task.toml").is_file())


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
