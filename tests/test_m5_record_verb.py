import json
import os
import subprocess
import sys

from conftest import smoke_agent_command


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
    env = {"EVAL_STUB": "1", "EVOLVE_HOME": str(home), "EVOLVE_AGENT_COMMAND": smoke_agent_command()}
    assert _evolve(["init", str(ws)], tmp_path, env).returncode == 0
    assert _evolve(["run", str(ws), "--max-generations", "1"], tmp_path, env).returncode == 0
    return ws, env


def test_record_rejects_stamped_and_identity_fields(tmp_path):
    ws, env = _init_and_run_one(tmp_path)
    before = (ws / "archive.jsonl").read_text()
    for bad in (
        {"score": 99.0},
        {"status": "complete"},
        {"tag": "gen/9"},
        {"genid": "7"},
        {"mutated": []},
        {"task_set_hash": "x"},
        {"evals": []},
        {"kind": "anchor"},
        {"round": 1},
        {"_evolve_mechanism_eval": True},
    ):
        result = _evolve(["record", str(ws), "1", "--fields", json.dumps(bad)], tmp_path, env)
        assert result.returncode != 0, f"accepted forbidden field {bad}"
    assert (ws / "archive.jsonl").read_text() == before
