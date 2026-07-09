from pathlib import Path

from conftest import git, init_workspace, rows_by_genid

from evolve.driver import RunOptions
from evolve.driver import run as driver_run


def test_hyperagents_meta_agent_change_affects_later_generation_not_current_one(
    tmp_path: Path, monkeypatch
) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))
    evolve_yaml = (workspace / "evolve.yaml").read_text()
    (workspace / "evolve.yaml").write_text(
        evolve_yaml.replace("    - target/**\n  exclude: []", "    - target/**\n    - operators/**\n  exclude: []")
    )
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
        "        agent.write_text(agent.read_text() + '\\n# first-child\\n')\n"
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
    assert "2" in rows
    assert "# later-child" in git(workspace, "show", "gen/2:target/agent.py")
