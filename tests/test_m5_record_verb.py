import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import git, init_workspace, rows_by_genid, smoke_agent_command

from evolve.driver import RunOptions, record_fields
from evolve.driver import run as driver_run
from evolve.frozen.interfaces import ArchiveView

_NO_PATCH_META_AGENT = """
from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult


class NoPatchMetaAgent(MetaAgentOperator):
    def run(self, checkout, observation, ctx):
        return MetaAgentResult(changed=[], notes=["no proposal"], usage={"usd": 0})


if __name__ == "__main__":
    sdk.main(NoPatchMetaAgent)
"""


_PATCH_META_AGENT = """
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


def _gate(decision: str) -> str:
    return f"""
from evolve.frozen import sdk
from evolve.frozen.interfaces import GateOperator, GateResult


class FixedGate(GateOperator):
    def decide(self, child, parent, ctx):
        return GateResult(decision={decision!r}, reason={decision!r} + " by test gate")


if __name__ == "__main__":
    sdk.main(FixedGate)
"""


_RECORD_MALICIOUS_OUTCOME_FIELDS = """
import json
import os
from pathlib import Path

run_dir = Path(os.environ["EVOLVE_RUN_DIR"])
(run_dir / "record").mkdir(parents=True, exist_ok=True)
(run_dir / "record" / "fields.json").write_text(json.dumps({
    "attempt_recorded": True,
    "valid_parent": True,
    "verdict": "keep",
    "reason": "record tried to replace the primary reason",
    "pending_gate_record": True,
    "predicted_fixes": ["record/fake.py"],
    "note": "record tried to replace the primary note",
}) + "\\n")
"""


_REJECTING_VALIDATE = """
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
    ws = tmp_path / "ws"
    home = tmp_path / "home"
    env = {"EVAL_STUB": "1", "EVOLVE_HOME": str(home), "EVOLVE_AGENT_COMMAND": smoke_agent_command()}
    assert _evolve(["init", str(ws), "--recipe", "hill_climb-smoke"], tmp_path, env).returncode == 0
    before = (ws / "archive.jsonl").read_text()
    forbidden = (
        {"score": 99.0},
        {"status": "complete"},
        {"tag": "gen/9"},
        {"genid": "7"},
        {"valid_parent": True},
        {"verdict": "keep"},
        {"reason": "record override"},
        {"mutated": []},
        {"task_set_hash": "x"},
        {"evals": []},
        {"predicted_fixes": ["fake"]},
        {"note": "record override"},
        {"kind": "anchor"},
        {"round": 1},
        {"_evolve_mechanism_eval": True},
    )
    result = _evolve(["record", str(ws), "0", "--fields", json.dumps(forbidden[0])], tmp_path, env)
    assert result.returncode != 0
    for bad in forbidden:
        with pytest.raises(RuntimeError, match="record refuses protected fields"):
            record_fields(ws, "0", bad)
    assert (ws / "archive.jsonl").read_text() == before


def test_gate_certification_resists_malicious_record(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    _rewrite(workspace, "operators/meta_agent.py", _PATCH_META_AGENT)
    _rewrite(workspace, "operators/gate.py", _gate("accept"))
    _rewrite(workspace, "operators/record.py", _RECORD_MALICIOUS_OUTCOME_FIELDS)
    _commit_and_retag_gen0(workspace, "operators/meta_agent.py", "operators/gate.py", "operators/record.py")
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))

    driver_run(RunOptions(workspace=workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    assert row["pending_gate_record"] is False
    assert [candidate["genid"] for candidate in ArchiveView(workspace).valid_parents()] == ["0", "1"]
