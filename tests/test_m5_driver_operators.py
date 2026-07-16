import json
import random
import runpy
import shlex
import sys
from pathlib import Path

from conftest import git, init_miniswe_workspace, init_workspace, rows_by_genid, run_evolve, smoke_env

from evolve.archive import MECHANISM_EVAL_FIELD, append_event, eval_receipt_path, read_events
from evolve.config import load_config, render_yaml
from evolve.driver import RunOptions
from evolve.driver import run as driver_run
from evolve.frozen.interfaces import OperatorContext

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


def _rewrite(workspace: Path, relative_path: str, content: str) -> None:
    path = workspace / relative_path
    path.write_text(content)


def _commit_and_retag_gen0(workspace: Path, *paths: str) -> None:
    git(workspace, "add", *paths)
    git(workspace, "commit", "-m", "adjust gen 0 scaffolding")
    git(workspace, "tag", "-f", "gen/0")


def _rewrite_baseline_task_failure(workspace: Path, evolve_home: Path) -> None:
    local = workspace / "archive.jsonl"
    parent = next(
        event for event in read_events(local) if event.get("genid") == "0" and event.get(MECHANISM_EVAL_FIELD) is True
    )
    parent["task_vector"]["tasks"]["task-0"]["trials"][0]["reward"] = 0.0
    parent["note"] = "baseline evaluated"
    mirror = evolve_home / "mirrors" / workspace.name / "archive.jsonl"
    for archive in (local, mirror):
        archive.write_text("")
        eval_receipt_path(archive).unlink(missing_ok=True)
    append_event(workspace, workspace.name, parent)


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
    row = rows_by_genid(workspace)["1"]
    assert row["reason"] == "score 1.0 >= parent 1.0"
    assert row["note"] == "variant: hyperagents"


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


def test_validate_rejection_happens_before_candidate_commit(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    _rewrite(workspace, "operators/validate.py", _REJECTING_VALIDATE)
    config = (workspace / "evolve.yaml").read_text().replace("  gate: {}\n", "  validate: {}\n  gate: {}\n")
    assert "  validate: {}\n" in config
    _rewrite(workspace, "evolve.yaml", config)
    _commit_and_retag_gen0(workspace, "operators/validate.py", "evolve.yaml")
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_env(evolve_home)["EVOLVE_AGENT_COMMAND"])

    driver_run(RunOptions(workspace=workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    assert row["status"] == "rejected_validation"
    assert row["reason"] == "candidate validation rejected: broken imports"
    assert not git(workspace, "tag", "--list", "gen/1")
    assert json.loads((workspace / "runs/gen-1/validate/result.json").read_text())["accept"] is False


def test_driver_has_no_package_manager_specific_admission(tmp_path: Path) -> None:
    workspace, evolve_home = init_miniswe_workspace(tmp_path)
    # This test exercises admission, not the real recipe's Harbor evidence path.
    _rewrite(workspace, "operators/rollout.py", (workspace / "library/rollout/noop.py").read_text())
    _rewrite(workspace, "operators/meta_agent.py", (workspace / "library/meta_agent/hyperagents.py").read_text())
    config = load_config(workspace / "evolve.yaml")
    del config["operators"]["trace_analyzer"]
    config["operators"]["meta_agent"]["runner"] = "local"
    _rewrite(workspace, "evolve.yaml", render_yaml(config))
    _commit_and_retag_gen0(workspace, "operators/rollout.py", "operators/meta_agent.py", "evolve.yaml")
    code = (
        "from pathlib import Path\n"
        "path = Path('target/pyproject.toml')\n"
        "path.write_text(path.read_text() + '\\n# dependency metadata changed\\n')\n"
        "print('predicted_fixes: []')\n"
    )
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={
            "EVAL_STUB": "1",
            "EVOLVE_HOME": str(evolve_home),
            "EVOLVE_AGENT_COMMAND": command,
        },
    )

    assert result.returncode == 0, result.stderr
    row = rows_by_genid(workspace)["1"]
    assert row["mutated"] == ["target/pyproject.toml"]
    assert git(workspace, "tag", "--list", "gen/1") == "gen/1"


def test_jsonl_record_computes_verified_fixes_from_task_vectors(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    baseline = run_evolve("run", str(workspace), "--max-generations", "0", env=smoke_env(evolve_home))
    assert baseline.returncode == 0, baseline.stderr
    _rewrite_baseline_task_failure(workspace, evolve_home)

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
    baseline = run_evolve("run", str(workspace), "--max-generations", "0", env=smoke_env(evolve_home))
    assert baseline.returncode == 0, baseline.stderr
    _rewrite_baseline_task_failure(workspace, evolve_home)

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
