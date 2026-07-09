import os
import subprocess
import sys


def _evolve(args, cwd, env_extra=None):
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [sys.executable, "-m", "evolve", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )


def _init_and_run_one(tmp_path):
    ws = tmp_path / "ws"
    home = tmp_path / "home"
    env = {"EVAL_STUB": "1", "EVOLVE_HOME": str(home)}
    assert _evolve(["init", str(ws), "--recipe", "hill_climb-smoke"], tmp_path, env).returncode == 0
    assert _evolve(["run", str(ws), "--max-generations", "1"], tmp_path, env).returncode == 0
    return ws, env


def test_sdk_rows_and_best_ever(tmp_path, monkeypatch):
    ws, _env = _init_and_run_one(tmp_path)
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    from evolve.frozen import sdk

    rows = sdk.rows(ws)
    assert [r["genid"] for r in rows] == ["0", "1"]
    best = sdk.best_ever(ws)
    assert best is not None and best["score"] == 1.0
    assert sdk.row(ws, "1")["status"] == "complete"
    assert {r["genid"] for r in sdk.valid_parents(ws)} == {"0", "1"}
    assert sdk.run_dir(ws, "1") == ws / "runs" / "gen-1"
