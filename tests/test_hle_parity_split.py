import hashlib
import json
from pathlib import Path

import pytest
from conftest import run_evolve, write_locked_miniswe_seed

from evolve.config import load_config
from evolve.splits import build_manifest


ROOT = Path(__file__).resolve().parents[1]
SPLIT_DIR = ROOT / "experiments" / "hle-parity-100-49-100"
SPLIT_NAMES = ("train", "gate", "sealed")
EXPECTED_COUNTS = {"train": 100, "gate": 49, "sealed": 100}
EXPECTED_RATIOS = {
    "train": 0.40160642570281124,
    "gate": 0.19678714859437751,
    "sealed": 0.40160642570281124,
}


def _lines(name: str) -> list[str]:
    return (SPLIT_DIR / name).read_text().splitlines()


def _digest(split_name: str, names: list[str]) -> str:
    payload = json.dumps(
        {"split": split_name, "tasks": sorted(names)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def test_hle_parity_shared_split_is_complete_and_reproducible(tmp_path: Path) -> None:
    manifest = json.loads((SPLIT_DIR / "split.json").read_text())
    source_names = _lines("source-task-names.txt")
    split_names = {name: _lines(f"{name}.txt") for name in SPLIT_NAMES}

    assert manifest["version"] == 1
    assert manifest["source"] == {
        "task_count": 249,
        "url": "https://github.com/harbor-framework/harbor/blob/main/adapters/hle/run_hle_parity.yaml",
        "blob_sha": "ac0147d4a5f748810a9567ac9f6d257aa1fd9b74",
    }
    assert manifest["algorithm"] == "evolve.splits.build_manifest/v1"
    assert manifest["seed"] == 42
    assert manifest["ratios"] == EXPECTED_RATIOS
    assert manifest["counts"] == EXPECTED_COUNTS
    assert len(source_names) == len(set(source_names)) == 249
    assert all(name.startswith("hle__") for name in source_names)

    sets = {name: set(names) for name, names in split_names.items()}
    assert {name: len(names) for name, names in sets.items()} == EXPECTED_COUNTS
    assert not (sets["train"] & sets["gate"])
    assert not (sets["train"] & sets["sealed"])
    assert not (sets["gate"] & sets["sealed"])
    assert set(source_names) == set.union(*sets.values())
    assert manifest["tasks"] == split_names
    assert manifest["digests"] == {
        name: _digest(name, names) for name, names in split_names.items()
    }

    dataset = tmp_path / "hle-parity"
    dataset.mkdir()
    for name in source_names:
        task = dataset / name
        task.mkdir()
        (task / "task.toml").write_text(f'[task]\nname = "hle/{name}"\n')

    generated = build_manifest(
        str(dataset),
        {**EXPECTED_RATIOS, "seed": 42},
        base_dir=tmp_path,
        sampling="static",
        gate_limit=100,
    )
    assert generated["tasks"] == split_names


def test_hle_recipes_use_the_shared_split_without_changing_base_recipes() -> None:
    expected_split = {**EXPECTED_RATIOS, "seed": 42}
    for recipe_name in ("ahe_hle", "hyperagents_hle"):
        config = load_config(ROOT / "recipes" / recipe_name / "evolve.yaml")
        evaluator = config["evaluator"]
        assert evaluator["dataset"] == "hle_parity"
        assert evaluator["split"] == expected_split
        assert evaluator["sampling"] == "static"
        assert evaluator["evaluation_split"] == "train"
        assert evaluator["tasks_per_round"] == 100
        assert evaluator["n_concurrent"] == 25

    assert load_config(ROOT / "recipes" / "ahe" / "evolve.yaml")["evaluator"]["dataset"] == (
        "terminal-bench-2-50-19-20"
    )
    assert load_config(ROOT / "recipes" / "hyperagents" / "evolve.yaml")["evaluator"]["dataset"] == (
        "terminal-bench-2-50-19-20"
    )


@pytest.mark.parametrize("recipe_name", ["ahe_hle", "hyperagents_hle"])
def test_hle_recipe_initialization_freezes_shared_membership(tmp_path: Path, recipe_name: str) -> None:
    source_names = _lines("source-task-names.txt")
    dataset = tmp_path / "hle-parity"
    dataset.mkdir()
    for name in source_names:
        task = dataset / name
        task.mkdir()
        (task / "task.toml").write_text(f'[task]\nname = "hle/{name}"\n')
    seed = write_locked_miniswe_seed(tmp_path / "miniswe-seed")
    workspace = tmp_path / f"{recipe_name}-workspace"

    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        recipe_name,
        "--dataset",
        str(dataset),
        "--seed",
        str(seed),
    )

    assert result.returncode == 0, result.stderr
    generated = json.loads((workspace / "evaluator" / "splits.json").read_text())
    expected = json.loads((SPLIT_DIR / "split.json").read_text())
    assert generated["tasks"] == expected["tasks"]
