from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import evolve.run_summary as run_summary


def _config(*, validate: bool = False, target_score=None, children_per_gen: int = 1) -> dict:
    operators = {"validate": {"variant": "minibatch_improvement"}} if validate else {}
    return {
        "experiment": {"target_score": target_score, "children_per_gen": children_per_gen},
        "operators": operators,
    }


def _complete(genid: str, *, score: float = 1.0) -> dict:
    return {
        "genid": genid,
        "status": "complete",
        "outcome": "benchmark_complete",
        "pending_gate_record": False,
        "valid_parent": True,
        "verdict": "keep",
        "score": score,
        run_summary.RECEIPT_CERTIFIED_FIELD: True,
    }


def _stub_common(monkeypatch: pytest.MonkeyPatch, rows: list[dict], config: dict) -> None:
    monkeypatch.setattr(run_summary, "load_config", lambda _path: config)
    monkeypatch.setattr(run_summary, "merged_rows", lambda _path: rows)
    monkeypatch.setattr(run_summary, "verify_integrity", lambda _workspace: [])
    monkeypatch.setattr(run_summary, "tag_matches_candidate", lambda _workspace, _row, _genid: True)


def test_run_summary_accepts_complete_certified_lineage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_common(monkeypatch, [_complete("0"), _complete("1")], _config())

    summary = run_summary.build_run_summary(tmp_path, through=1)

    assert summary["status"] == "passed"
    assert [row["terminal_kind"] for row in summary["generations"]] == ["evaluated", "evaluated"]


def test_run_summary_accepts_recipe_validation_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_complete("0"), {"genid": "1", "status": "rejected_validation"}]
    _stub_common(monkeypatch, rows, _config(validate=True))
    result = tmp_path / "runs" / "gen-1" / "validate" / "result.json"
    result.parent.mkdir(parents=True)
    result.write_text(json.dumps({"accept": False, "reason": "strict minibatch did not improve"}))
    monkeypatch.setattr(run_summary, "git", lambda *_args, **_kwargs: SimpleNamespace(returncode=1))

    summary = run_summary.build_run_summary(tmp_path, through=1)

    assert summary["status"] == "passed"
    assert summary["generations"][-1]["terminal_kind"] == "validation_rejected"


@pytest.mark.parametrize("status", ["operator_failed", "no_proposal", "invalid_proposal", "partial"])
def test_run_summary_rejects_non_success_terminal_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    _stub_common(monkeypatch, [_complete("0"), {"genid": "1", "status": status}], _config())

    summary = run_summary.build_run_summary(tmp_path, through=1)

    assert summary["status"] == "failed"
    assert f"terminal status {status!r}" in summary["findings"][0]


def test_run_summary_requires_every_fanout_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_common(monkeypatch, [_complete("0"), _complete("1-0")], _config(children_per_gen=2))

    summary = run_summary.build_run_summary(tmp_path, through=1)

    assert summary["status"] == "failed"
    assert "expected child rows ['1-0', '1-1']" in summary["findings"][0]


def test_run_summary_allows_generations_after_target_was_reached_to_be_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_common(monkeypatch, [_complete("0", score=0.8)], _config(target_score=0.8))

    summary = run_summary.build_run_summary(tmp_path, through=3)

    assert summary["status"] == "passed"
    assert summary["target_reached_at"] == 0
