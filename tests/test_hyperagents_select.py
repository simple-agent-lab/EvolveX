from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_score_child_prop():
    path = Path(__file__).resolve().parents[1] / "library" / "select" / "score_child_prop.py"
    assert path.exists(), "library/select/score_child_prop.py is missing"
    spec = importlib.util.spec_from_file_location("score_child_prop", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "genid": "1", "valid_parent": True, "status": "complete", "score": 0.2,
            "outcome": "benchmark_complete", "selection_eligible": True,
        },
        {"genid": "2", "valid_parent": True, "status": "partial", "score": 0.5},
        {
            "genid": "3", "valid_parent": True, "status": "complete", "score": 0.8,
            "outcome": "benchmark_complete", "selection_eligible": True,
        },
        {
            "genid": "invalid-outcome", "valid_parent": True, "status": "complete", "score": 0.9,
            "outcome": "candidate_invalid", "selection_eligible": False,
        },
        {"genid": "invalid-parent", "valid_parent": False, "status": "complete", "score": 0.9},
        {"genid": "missing-score", "valid_parent": True, "status": "complete"},
        {"genid": "bool-score", "valid_parent": True, "status": "complete", "score": True},
    ]
    rows.extend({"genid": f"child-{i}", "parent": "3", "valid_parent": False} for i in range(9))
    return rows


def test_selection_weights_match_upstream_sigmoid_and_child_penalty() -> None:
    module = _load_score_child_prop()
    rows = _rows()
    valid = [row for row in rows if row.get("outcome") == "benchmark_complete"]

    weighted = dict(module.selection_weights(valid, rows))

    midpoint = (0.8 + 0.2) / 2
    assert weighted["1"] == pytest.approx(1 / (1 + math.exp(-10 * (0.2 - midpoint))))
    assert weighted["3"] == pytest.approx(
        (1 / (1 + math.exp(-10 * (0.8 - midpoint)))) * math.exp(-((9 / 8) ** 3))
    )

    assert "2" not in weighted
    assert "invalid-outcome" not in weighted
    assert "invalid-parent" not in weighted
    assert "missing-score" not in weighted
    assert "bool-score" not in weighted


def test_score_child_prop_selects_only_weighted_candidate_ids() -> None:
    module = _load_score_child_prop()
    rows = _rows()
    valid = [row for row in rows if row.get("outcome") == "benchmark_complete"]
    candidate_ids = {str(row["genid"]) for row in valid}
    archive = SimpleNamespace(rows=lambda: rows, valid_parents=lambda: valid)
    ctx = SimpleNamespace(rng=random.Random(0), fan_out=25)

    result = module.ScoreChildProportionalSelect().pick(archive, ctx)

    assert set(result.parents).issubset(candidate_ids)
    assert len(result.parents) == 25
