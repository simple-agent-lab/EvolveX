from pathlib import Path

from conftest import git, git_show, rows_by_genid, run_evolve

from evolve.driver import RunOptions
from evolve.driver import run as driver_run
from evolve.population import valid_parent_rows


def _init_hyperagents_smoke(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "hyperagents-smoke"
    evolve_home = tmp_path / "evolve-home"
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hyperagents-smoke",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert result.returncode == 0, result.stderr
    return workspace, evolve_home


def _write_newest_select(workspace: Path) -> None:
    (workspace / "operators" / "select.py").write_text(
        "import os, sys\n"
        "sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]\n"
        "from evolve.frozen import sdk\n"
        "from evolve.frozen.interfaces import SelectOperator, SelectResult\n"
        "class S(SelectOperator):\n"
        "    def pick(self, archive, ctx):\n"
        "        parents = archive.valid_parents()\n"
        "        chosen = max(parents, key=lambda row: int(str(row['genid']).split('-', 1)[0]))\n"
        "        return SelectResult(parents=[str(chosen['genid'])])\n"
        "if __name__ == '__main__':\n"
        "    sdk.main(S)\n"
    )


def test_hyperagents_meta_agent_change_affects_later_generation_not_current_one(
    tmp_path: Path, monkeypatch
) -> None:
    workspace, evolve_home = _init_hyperagents_smoke(tmp_path)
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))
    _write_newest_select(workspace)
    (workspace / "operators" / "select.py").write_text(
        "import os, sys\n"
        "sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]\n"
        "from evolve.frozen import sdk\n"
        "from evolve.frozen.interfaces import SelectOperator, SelectResult\n"
        "class S(SelectOperator):\n"
        "    def pick(self, archive, ctx):\n"
        "        parents = archive.valid_parents()\n"
        "        chosen = max(parents, key=lambda row: int(str(row['genid']).split('-', 1)[0]))\n"
        "        return SelectResult(parents=[str(chosen['genid'])])\n"
        "if __name__ == '__main__':\n"
        "    sdk.main(S)\n"
    )
    (workspace / "operators" / "meta_agent.py").write_text(
        "import os, sys\n"
        "sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]\n"
        "from evolve.frozen import sdk\n"
        "from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult\n"
        "class M(MetaAgentOperator):\n"
        "    def run(self, checkout, observation, ctx):\n"
        "        script = checkout / 'operators' / 'meta_agent.py'\n"
        "        script.write_text(script.read_text().replace('first-child', 'later-child'))\n"
        "        agent = checkout / 'target' / 'agent.py'\n"
        "        agent.write_text(agent.read_text() + '\\n# first-child\\n# FAIL task-0\\n')\n"
        "        return MetaAgentResult(changed=['operators/meta_agent.py', 'target/agent.py'], notes=['self changed'], usage={'usd': 0})\n"
        "if __name__ == '__main__':\n"
        "    sdk.main(M)\n"
    )
    git(workspace, "add", "-A")
    git(workspace, "commit", "-qm", "enable hyperagents test")
    git(workspace, "tag", "-f", "gen/0")

    driver_run(RunOptions(workspace=workspace, max_generations=2, children_per_gen=1))

    rows = rows_by_genid(workspace)
    assert "1" in rows
    assert "# first-child" in git(workspace, "show", "gen/1:target/agent.py")
    assert rows["1"]["status"] == "complete"
    assert rows["1"]["valid_parent"] is True
    assert rows["1"]["score"] < rows["0"]["score"]
    assert "2" in rows
    assert "# later-child" in git(workspace, "show", "gen/2:target/agent.py")
    assert rows["2"]["parent"] == "1"
    assert {str(row["genid"]) for row in valid_parent_rows(workspace)} >= {"0", "1", "2"}
    assert list((workspace / "runs/evaluations/candidate/gen-1").glob("candidate-*/attempt-1"))
    assert not (workspace / "runs" / "gen-1" / "eval-stage").exists()
    assert not (workspace / "runs" / "gen-1" / "meta_eval.json").exists()

    for operator in ("validate", "record"):
        assert git_show(workspace, f"gen/0:operators/{operator}.py") == git_show(
            workspace, f"gen/1:operators/{operator}.py"
        )
        assert git_show(workspace, f"gen/1:operators/{operator}.py") == git_show(
            workspace, f"gen/2:operators/{operator}.py"
        )
