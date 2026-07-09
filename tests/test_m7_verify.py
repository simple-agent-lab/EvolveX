"""`evolve verify` — integrity fsck that exposes a hand-edited ledger (DESIGN
observability)."""

from pathlib import Path

from conftest import init_workspace, run_evolve

from evolve.archive import MECHANISM_EVAL_FIELD, append_event


def _mechanism_eval_event() -> dict:
    return {
        "genid": "1",
        "parent": "0",
        "tag": "gen/1",
        "score": 0.9,
        "status": "complete",
        "task_set_hash": "h",
        "task_vector": {"task-0": True},
        "evaluator_tree": "t",
        "valid_parent": True,
        "verdict": "keep",
        "reason": "r",
        "cost": {"usd": 0, "wall_s": 0},
        "round": 0,
        MECHANISM_EVAL_FIELD: True,
    }


def test_verify_passes_clean_ledger_and_flags_tampering(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    workspace, _ = init_workspace(tmp_path)
    # a legit mechanism-eval writes a tamper-evident receipt
    append_event(workspace, "experiment", _mechanism_eval_event())

    clean = run_evolve("verify", str(workspace), env={"EVOLVE_HOME": str(tmp_path / "home")})
    assert clean.returncode == 0, clean.stderr
    assert "integrity: ok" in clean.stdout

    # hand-edit the score in the ledger — its receipt no longer matches
    archive = workspace / "archive.jsonl"
    archive.write_text(archive.read_text().replace('"score": 0.9', '"score": 999.0'))

    tampered = run_evolve("verify", str(workspace), env={"EVOLVE_HOME": str(tmp_path / "home")})
    assert tampered.returncode == 1
    assert "TAMPER" in tampered.stderr
    assert "hand-edited" in tampered.stderr
