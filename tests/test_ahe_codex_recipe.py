from __future__ import annotations

import json
from pathlib import Path

from evolve.config import load_config

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "recipes" / "ahe_codex"


def test_ahe_codex_dataset_manifest_is_versioned_and_content_bound() -> None:
    manifest = json.loads((RECIPE / "dataset-manifest.json").read_text())

    assert manifest["version"] == 1
    assert manifest["dataset"] == "terminal-bench@2.0"
    assert manifest["name"] == "terminal-bench-2-ahe-30-v1"
    assert manifest["selection"] == {
        "count": 30,
        "scheme": "sha256-order-v1",
        "seed": "terminal-bench@2.0 + NUL + ahe-codex-30-v1 + NUL",
    }
    tasks = manifest["tasks"]
    assert len(tasks) == 30
    assert list(tasks) == sorted(tasks)
    assert all(digest.startswith("sha256:") and len(digest) == 71 for digest in tasks.values())


def test_ahe_codex_recipe_uses_the_pinned_manifest_identity() -> None:
    manifest = json.loads((RECIPE / "dataset-manifest.json").read_text())
    recipe = load_config(RECIPE / "evolve.yaml")

    assert recipe["target"]["seed"] == "builtin-codex"
    assert recipe["evaluator"]["dataset"] == manifest["name"]
    assert recipe["evaluator"]["tasks_per_round"] == manifest["selection"]["count"]
    assert recipe["evaluator"]["agent"] == "target.agent:HarborAgent"
    assert recipe["operators"]["meta_agent"]["agent"] == "codex"
    assert recipe["operators"]["meta_agent"]["editable_roots"] == ["target"]
