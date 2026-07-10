import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import git, init_workspace, rows_by_genid, smoke_agent_command

from evolve.archive import archive_path, read_events
from evolve.config import experiment_id, operator_blocks
from evolve.driver import RunOptions
from evolve.driver import _run_terminal_record
from evolve.driver import run as driver_run


_NO_PATCH_META_AGENT = """
import os
import sys
sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult


class NoPatchMetaAgent(MetaAgentOperator):
    def run(self, checkout, observation, ctx):
        return MetaAgentResult(changed=[], notes=["no proposal"], usage={"usd": 0})


if __name__ == "__main__":
    sdk.main(NoPatchMetaAgent)
"""


_PATCH_META_AGENT = """
import os
import sys
sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult


class PatchMetaAgent(MetaAgentOperator):
    def run(self, checkout, observation, ctx):
        target = checkout / "target" / "agent.py"
        target.write_text(target.read_text() + "\\n# validation candidate\\n")
        return MetaAgentResult(changed=["target/agent.py"], notes=["candidate"], usage={"usd": 0})


if __name__ == "__main__":
    sdk.main(PatchMetaAgent)
"""


_RECORD_ATTEMPT = """
import json
import os
from pathlib import Path

run_dir = Path(os.environ["EVOLVE_RUN_DIR"])
(run_dir / "record").mkdir(parents=True, exist_ok=True)
(run_dir / "record" / "fields.json").write_text(json.dumps({"attempt_recorded": True}) + "\\n")
"""


_RECORD_FAILS = """
raise SystemExit("record exploded")
"""


_REJECTING_VALIDATE = """
import os
import sys
sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import ValidateOperator, ValidateResult


class RejectingValidate(ValidateOperator):
    def validate(self, checkout, ctx):
        return ValidateResult(accept=False, reason="broken imports", artifacts=[])


if __name__ == "__main__":
    sdk.main(RejectingValidate)
"""


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


def _rewrite(workspace: Path, relative_path: str, content: str) -> None:
    (workspace / relative_path).write_text(content)


def _commit_and_retag_gen0(workspace: Path, *paths: str) -> None:
    git(workspace, "add", *paths)
    git(workspace, "commit", "-m", "adjust gen 0 operators")
    git(workspace, "tag", "-f", "gen/0")


def _enable_validate(config: str) -> str:
    if "  validate: {}\n" in config:
        return config
    return config.replace("  gate: {}\n", "  validate: {}\n  gate: {}\n")


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


def test_run_records_rejected_no_proposal_attempt(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    _rewrite(workspace, "operators/meta_agent.py", _NO_PATCH_META_AGENT)
    _rewrite(workspace, "operators/record.py", _RECORD_ATTEMPT)
    _commit_and_retag_gen0(workspace, "operators/meta_agent.py", "operators/record.py")
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))

    driver_run(RunOptions(workspace=workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    assert row["status"] == "no_proposal"
    assert row["attempt_recorded"] is True
    assert json.loads((workspace / "runs/gen-1/record/fields.json").read_text()) == {
        "attempt_recorded": True
    }


def test_successful_terminal_record_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    _rewrite(workspace, "operators/meta_agent.py", _NO_PATCH_META_AGENT)
    _rewrite(workspace, "operators/record.py", _RECORD_ATTEMPT)
    _commit_and_retag_gen0(workspace, "operators/meta_agent.py", "operators/record.py")
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))

    driver_run(RunOptions(workspace=workspace, max_generations=1))
    _run_terminal_record(
        workspace,
        experiment_id(workspace),
        "1",
        "0",
        operator_blocks(workspace),
        candidate_checkout=None,
    )

    record_events = [
        event
        for event in read_events(archive_path(workspace))
        if event.get("genid") == "1" and event.get("attempt_recorded") is True
    ]
    assert len(record_events) == 1


def test_record_failure_preserves_validation_rejection_status(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    _rewrite(workspace, "operators/meta_agent.py", _PATCH_META_AGENT)
    _rewrite(workspace, "operators/validate.py", _REJECTING_VALIDATE)
    _rewrite(workspace, "operators/record.py", _RECORD_FAILS)
    _rewrite(workspace, "evolve.yaml", _enable_validate((workspace / "evolve.yaml").read_text()))
    _commit_and_retag_gen0(
        workspace,
        "operators/meta_agent.py",
        "operators/validate.py",
        "operators/record.py",
        "evolve.yaml",
    )
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))

    driver_run(RunOptions(workspace=workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    assert row["status"] == "rejected_validation"
    assert row["reason"].startswith("candidate validation rejected")
    assert "record_error" in row
