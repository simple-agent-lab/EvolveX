import json
import random
import runpy
from pathlib import Path

from conftest import git, init_workspace, rows_by_genid, run_evolve, smoke_env

from evolve.frozen.interfaces import OperatorContext


def _rewrite(workspace: Path, relative_path: str, content: str) -> None:
    path = workspace / relative_path
    path.write_text(content)


def _commit_and_retag_gen0(workspace: Path, *paths: str) -> None:
    git(workspace, "add", *paths)
    git(workspace, "commit", "-m", "adjust gen 0 scaffolding")
    git(workspace, "tag", "-f", "gen/0")


def test_run_uses_operator_subprocesses_for_loop_steps(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env=smoke_env(evolve_home),
    )

    assert result.returncode == 0, result.stderr
    run_dir = workspace / "runs" / "gen-1"
    assert "written-by: operators/meta_agent.py" in (run_dir / "meta_agent" / "rationale.md").read_text()
    assert json.loads((run_dir / "gate.json").read_text())["verdict"] == "keep"
    assert (run_dir / "feedback" / "index.md").exists()
    row = rows_by_genid(workspace)["1"]
    assert row["reason"] == "score 1.0 >= parent 1.0"
    assert row["note"] == "variant: agent_command"


def test_run_records_operator_failed_when_meta_agent_operator_crashes(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    _rewrite(workspace, "operators/meta_agent.py", "raise SystemExit(1)\n")
    _commit_and_retag_gen0(workspace, "operators/meta_agent.py")

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env=smoke_env(evolve_home),
    )

    assert result.returncode == 0, result.stderr
    row = rows_by_genid(workspace)["1"]
    assert row["status"] == "operator_failed"
    assert row["valid_parent"] is False
    assert row["verdict"] == "discard"
    assert row["reason"] == "operator meta_agent failed"


def test_jsonl_record_computes_verified_fixes_from_task_vectors(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    parent = rows_by_genid(workspace)["0"]
    parent["task_vector"]["task-0"] = False
    (workspace / "archive.jsonl").write_text(json.dumps(parent) + "\n")

    _rewrite(
        workspace,
        "operators/meta_agent.py",
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "run_dir = Path(os.environ['EVOLVE_RUN_DIR']) / 'meta_agent'\n"
        "run_dir.mkdir(parents=True, exist_ok=True)\n"
        "(run_dir / 'predicted_fixes.json').write_text(json.dumps(['task-0']))\n"
        "(run_dir / 'usage.json').write_text(json.dumps({'usd': 0}))\n"
        "Path('target/agent.py').write_text(Path('target/agent.py').read_text() + '\\n# update\\n')\n",
    )
    _commit_and_retag_gen0(workspace, "operators/meta_agent.py")

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env=smoke_env(evolve_home),
    )

    assert result.returncode == 0, result.stderr
    assert rows_by_genid(workspace)["1"]["verified_fixes"] == ["task-0"]


def test_driver_does_not_inject_verified_fixes_for_other_record_operators(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    parent = rows_by_genid(workspace)["0"]
    parent["task_vector"]["task-0"] = False
    (workspace / "archive.jsonl").write_text(json.dumps(parent) + "\n")

    _rewrite(
        workspace,
        "operators/meta_agent.py",
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "run_dir = Path(os.environ['EVOLVE_RUN_DIR']) / 'meta_agent'\n"
        "run_dir.mkdir(parents=True, exist_ok=True)\n"
        "(run_dir / 'predicted_fixes.json').write_text(json.dumps(['task-0']))\n"
        "(run_dir / 'usage.json').write_text(json.dumps({'usd': 0}))\n"
        "Path('target/agent.py').write_text(Path('target/agent.py').read_text() + '\\n# update\\n')\n",
    )
    _rewrite(
        workspace,
        "operators/record.py",
        "from evolve.frozen import sdk\n"
        "from evolve.frozen.interfaces import RecordOperator, RecordResult\n"
        "\n"
        "class BareRecord(RecordOperator):\n"
        "    def annotate(self, child, ctx):\n"
        "        return RecordResult(fields={\n"
        "            'valid_parent': True,\n"
        "            'verdict': 'keep',\n"
        "            'reason': 'score 1.0 >= parent 1.0',\n"
        "            'predicted_fixes': ['task-0'],\n"
        "        })\n"
        "\n"
        "sdk.main(BareRecord)\n",
    )
    _commit_and_retag_gen0(workspace, "operators/meta_agent.py", "operators/record.py")

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env=smoke_env(evolve_home),
    )

    assert result.returncode == 0, result.stderr
    assert "verified_fixes" not in rows_by_genid(workspace)["1"]


def test_jsonl_record_omits_verified_fixes_when_prediction_artifact_is_missing(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    run_dir = workspace / "runs" / "record-without-predictions"
    run_dir.mkdir(parents=True)
    (run_dir / "gate.json").write_text(
        json.dumps({"valid_parent": True, "verdict": "keep", "reason": "no predictions"}) + "\n"
    )
    ctx = OperatorContext(
        workspace=workspace,
        checkout=workspace,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={},
        rng=random.Random(0),
    )
    child = {
        "genid": "1",
        "parent": "0",
        "predicted_fixes": [],
        "task_vector": {"task-0": True},
    }
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "library" / "record" / "jsonl.py"))

    fields = module["JsonlRecord"]().annotate(child, ctx).fields

    assert "verified_fixes" not in fields
