"""Self-modification admission gate (mechanism 1, DESIGN §2/§7): a confound-free
replay admits or reverts operator-surface changes.

Note: the stub harness scores every generation 1.0, so a replay can never make
the new operators look *worse* — meta_eval always admits under the stub (real
score-based rejection needs a live harness). So the driver's revert path is
tested by mocking `admit`, and the admit-keep path is exercised for real.
"""

import subprocess
from pathlib import Path

from conftest import init_workspace, rows_by_genid

from evolve.driver import RunOptions
from evolve.driver import run as driver_run
from evolve.frozen import meta_eval

# A mutate operator that edits the operator surface (operators/select.py) and the
# candidate (target/agent.py), so we can watch the operator part get reverted
# while the candidate part survives.
_SELF_MOD_MUTATE = """
import os
import sys
sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]
from evolve.frozen import sdk
from evolve.frozen.interfaces import MutateOperator, MutateResult


class SelfModMutate(MutateOperator):
    def mutate(self, checkout, observation, ctx):
        sel = checkout / "operators" / "select.py"
        sel.write_text(sel.read_text() + "\\n# self-mod operator edit\\n")
        agent = checkout / "target" / "agent.py"
        agent.write_text(agent.read_text() + "\\n# candidate edit\\n")
        return MutateResult(changed=["operators/select.py", "target/agent.py"], notes=["self-mod"], usage={"usd": 0})


if __name__ == "__main__":
    sdk.main(SelfModMutate)
"""


def _git(workspace: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(workspace), *args], text=True, capture_output=True, check=True)
    return result.stdout


def _setup_self_mod_workspace(tmp_path: Path) -> tuple[Path, Path]:
    workspace, evolve_home = init_workspace(tmp_path)
    (workspace / "operators" / "mutate.py").write_text(_SELF_MOD_MUTATE)
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


def test_meta_eval_admits_noninferior_operator_edit(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    sel = workspace / "operators" / "select.py"
    sel.write_text(sel.read_text() + "\n# harmless comment\n")
    verdict = meta_eval.admit(workspace, "gen/0", workspace, k=2)
    assert verdict["admitted"] is True, verdict
    assert verdict["old_best"] == 1.0 and verdict["new_best"] == 1.0


def test_driver_reverts_rejected_operator_change_but_keeps_candidate(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = _setup_self_mod_workspace(tmp_path)
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))
    # Force the admission gate to reject (the stub can't reject on score).
    monkeypatch.setattr(meta_eval, "admit", lambda *a, **k: {"admitted": False, "error": "forced-for-test"})
    driver_run(RunOptions(workspace=workspace, max_generations=1, children_per_gen=1))

    child = rows_by_genid(workspace).get("1")
    assert child is not None, "gen 1 was not recorded"
    assert child.get("operator_reverted") is True, child
    # operator change reverted, candidate change kept
    assert "self-mod operator edit" not in _git(workspace, "show", "gen/1:operators/select.py")
    assert "candidate edit" in _git(workspace, "show", "gen/1:target/agent.py")
