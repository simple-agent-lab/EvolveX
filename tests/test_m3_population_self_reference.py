import py_compile
from pathlib import Path

from conftest import git, git_show, init_workspace, rows_by_genid, run_evolve


def install_self_referential_mutate(workspace: Path) -> None:
    (workspace / "operators" / "mutate.py").write_text(
        "#!/usr/bin/env python3\n"
        "import argparse\n"
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--config', required=True)\n"
        "json.loads(parser.parse_args().config)\n"
        "genid = os.environ['EVOLVE_GENID']\n"
        "safe = genid.replace('-', '_')\n"
        "agent = Path('target/agent.py')\n"
        "agent.write_text(agent.read_text() + '\\nEVOLVE_GENERATION_%s = \"%s\"\\n' % (safe, genid))\n"
        "gate = Path('operators/gate.py')\n"
        'needle = \'return GateResult(decision="accept" if keep else "reject", reason=reason)\'\n'
        'replacement = \'return GateResult(decision="accept" if keep else "reject", reason=reason + " evolved")\'\n'
        "gate.write_text(gate.read_text().replace(needle, replacement))\n"
        "mutate_dir = Path(os.environ['EVOLVE_RUN_DIR']) / 'mutate'\n"
        "mutate_dir.mkdir(parents=True, exist_ok=True)\n"
        "(mutate_dir / 'rationale.md').write_text('written-by: operators/mutate.py\\nvariant: self-reference\\n')\n"
        "(mutate_dir / 'predicted_fixes.json').write_text('[]\\n')\n"
        "(mutate_dir / 'usage.json').write_text('{\"usd\": 0}\\n')\n"
    )


def test_population_fanout_creates_branching_lineage(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "2",
        "--children-per-gen",
        "2",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    rows = rows_by_genid(workspace)
    assert {"0", "1-0", "1-1", "2-0", "2-1"} <= set(rows)
    assert [rows[genid]["parent"] for genid in ("1-0", "1-1")] == ["0", "0"]
    assert all(rows[genid]["status"] == "complete" for genid in ("1-0", "1-1", "2-0", "2-1"))
    assert all(rows[genid]["valid_parent"] is True for genid in ("1-0", "1-1", "2-0", "2-1"))
    tagged_agent = tmp_path / "agent_gen_1_0.py"
    tagged_agent.write_text(git_show(workspace, "gen/1-0:target/agent.py").decode())
    py_compile.compile(str(tagged_agent), doraise=True)


def test_out_of_surface_operator_edit_is_caught_and_recorded(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    install_self_referential_mutate(workspace)
    git(workspace, "add", "operators/mutate.py")
    git(workspace, "commit", "-m", "attempt out-of-surface operator edit")
    git(workspace, "tag", "-f", "gen/0")

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={
            "EVAL_STUB": "1",
            "EVOLVE_HOME": str(evolve_home),
        },
    )

    assert result.returncode == 0, result.stderr
    rows = rows_by_genid(workspace)
    child = rows["1"]
    assert child["status"] == "invalid_proposal"
    assert child["valid_parent"] is False
    assert "operators/gate.py" in child["surface_violations"]
