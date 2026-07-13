"""Self-modification admission gate (mechanism 1, DESIGN §2/§7): a confound-free
replay admits or rejects operator-surface changes.

Note: the stub harness scores every generation 1.0, so a replay can never make
the new operators look *worse* — meta_eval always admits under the stub (real
score-based rejection needs a live harness). So the driver's rejection path is
tested by mocking `admit`, and the admit-keep path is exercised for real.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import init_workspace, rows_by_genid

from evolve.driver import RunOptions
from evolve.driver import run as driver_run
from evolve.frozen import meta_eval

# A meta-agent operator that edits itself and the target so a rejected admission
# proves the complete child is discarded atomically.
_SELF_MOD_META_AGENT = """
import os
import sys
sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]
from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult


class SelfModMetaAgent(MetaAgentOperator):
    def run(self, checkout, observation, ctx):
        workflow = checkout / "operators" / "meta_agent.py"
        workflow_marker = "child-" + "workflow-change"
        workflow.write_text(workflow.read_text() + "\\n# " + workflow_marker + "\\n")
        agent = checkout / "target" / "agent.py"
        agent.write_text(agent.read_text() + "\\n# child-target-change\\n")
        return MetaAgentResult(changed=["operators/meta_agent.py", "target/agent.py"], notes=["self-mod"], usage={"usd": 0})


if __name__ == "__main__":
    sdk.main(SelfModMetaAgent)
"""


def _git(workspace: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(workspace), *args], text=True, capture_output=True, check=True)
    return result.stdout


def _setup_self_mod_workspace(tmp_path: Path) -> tuple[Path, Path]:
    workspace, evolve_home = init_workspace(tmp_path)
    (workspace / "operators" / "meta_agent.py").write_text(_SELF_MOD_META_AGENT)
    yaml = (
        (workspace / "evolve.yaml")
        .read_text()
        .replace(
            "    - target/**\n  exclude: []",
            "    - target/**\n    - operators/**\n  exclude: []",
        )
    )
    assert "operators/**" in yaml, "surface include patch did not apply"
    (workspace / "evolve.yaml").write_text(yaml)
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-qm", "self-mod setup")
    _git(workspace, "tag", "-f", "gen/0")
    return workspace, evolve_home


def test_meta_eval_replay_does_not_inject_eval_stub(tmp_path: Path, monkeypatch) -> None:
    captured_env = {}
    captured_timeouts = []

    def fake_sh(cmd, cwd, *, check=True, env=None, timeout=600):
        if cmd[:3] == [sys.executable, "-m", "evolve"]:
            captured_env.update(env or {})
            captured_timeouts.append(timeout)
            (cwd / "archive.jsonl").write_text(json.dumps({"score": 1.0}) + "\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.delenv("EVAL_STUB", raising=False)
    monkeypatch.setattr(meta_eval, "_sh", fake_sh)

    score = meta_eval._replay(tmp_path, k=1, seed="s", timeout_s=1234)

    assert score == 1.0
    assert "EVAL_STUB" not in captured_env
    assert captured_env["EVOLVE_HOME"] == str(tmp_path / ".meta-home")
    assert captured_timeouts == [1234]


def test_meta_eval_timeout_terminates_the_replay_process_group(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    script = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        "time.sleep(60)"
    )
    child_pid = None
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            meta_eval._sh([sys.executable, "-c", script], tmp_path, timeout=1.0)
        child_pid = int(child_pid_path.read_text())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            pytest.fail("meta-eval timeout left its child process running")
    finally:
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_meta_eval_interrupt_terminates_the_replay_process_group(tmp_path: Path, monkeypatch) -> None:
    class InterruptedProcess:
        pid = 123
        returncode = -signal.SIGTERM
        calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise KeyboardInterrupt
            return "", ""

    killed = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: InterruptedProcess())
    monkeypatch.setattr(os, "killpg", lambda pid, sig: killed.append((pid, sig)))

    with pytest.raises(KeyboardInterrupt):
        meta_eval._sh(["replay"], tmp_path)

    assert killed == [(123, signal.SIGTERM)]


def test_meta_eval_repeated_interrupt_kills_and_reaps_the_replay_process_group(tmp_path: Path, monkeypatch) -> None:
    class RepeatedlyInterruptedProcess:
        pid = 234
        returncode = -signal.SIGKILL
        calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls < 3:
                raise KeyboardInterrupt
            return "", ""

    process = RepeatedlyInterruptedProcess()
    killed = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(os, "killpg", lambda pid, sig: killed.append((pid, sig)))

    with pytest.raises(KeyboardInterrupt):
        meta_eval._sh(["replay"], tmp_path)

    assert killed == [(234, signal.SIGTERM), (234, signal.SIGKILL)]
    assert process.calls == 3


def test_meta_eval_timeout_preserves_timeout_when_process_group_already_exited(tmp_path: Path, monkeypatch) -> None:
    class ExitedProcess:
        pid = 456
        returncode = -signal.SIGTERM
        calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(["replay"], timeout)
            return "", ""

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: ExitedProcess())
    monkeypatch.setattr(os, "killpg", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError))

    with pytest.raises(subprocess.TimeoutExpired):
        meta_eval._sh(["replay"], tmp_path, timeout=1)


def test_meta_eval_admits_noninferior_operator_edit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EVAL_STUB", "1")
    workspace, _ = init_workspace(tmp_path)
    sel = workspace / "operators" / "select.py"
    sel.write_text(sel.read_text() + "\n# harmless comment\n")
    verdict = meta_eval.admit(workspace, "gen/0", workspace, k=2)
    assert verdict["admitted"] is True, verdict
    assert verdict["old_best"] == 1.0 and verdict["new_best"] == 1.0


def test_driver_rejects_complete_child_when_self_modification_is_not_admitted(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = _setup_self_mod_workspace(tmp_path)
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))
    # Force the admission gate to reject (the stub can't reject on score).
    captured_admission = {}

    def reject_admission(*args, **kwargs):
        captured_admission.update(kwargs)
        return {"admitted": False, "error": "forced-for-test"}

    monkeypatch.setattr(meta_eval, "admit", reject_admission)
    monkeypatch.setattr(
        "evolve.driver.operator_timeout",
        lambda _config, name: 1234 if name == "meta_agent" else 600,
    )
    driver_run(RunOptions(workspace=workspace, max_generations=1, children_per_gen=1))

    rows = rows_by_genid(workspace)
    assert captured_admission["timeout_s"] == 1234
    assert rows["1"]["status"] == "rejected_admission"
    assert rows["1"]["valid_parent"] is False
    assert not _git(workspace, "tag", "--list", "gen/1")
    assert "child-target-change" not in _git(workspace, "show", "gen/0:target/agent.py")
    assert "child-workflow-change" not in _git(workspace, "show", "gen/0:operators/meta_agent.py")
