import json
import random
import runpy
from pathlib import Path

from conftest import git, init_workspace

from evolve.archive import MECHANISM_EVAL_FIELD, append_event, eval_receipt_path, read_events
from evolve.frozen.interfaces import OperatorContext

_REJECTING_VALIDATE = """
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

    assert "predicted_fixes" not in fields
    assert "verified_fixes" not in fields


def test_jsonl_record_allows_terminal_attempt_without_gate(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    run_dir = workspace / "runs" / "record-no-proposal"
    (run_dir / "meta_agent").mkdir(parents=True)
    (run_dir / "meta_agent" / "rationale.md").write_text("No source change was needed.\n")
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
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "library" / "record" / "jsonl.py"))

    fields = (
        module["JsonlRecord"]()
        .annotate({"genid": "1", "parent": "0", "status": "no_proposal", "reason": "no changes to commit"}, ctx)
        .fields
    )

    assert fields == {"note": "No source change was needed."}


def test_jsonl_record_preserves_explicit_optional_predictions(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    run_dir = workspace / "runs" / "record-with-predictions"
    (run_dir / "meta_agent").mkdir(parents=True)
    (run_dir / "gate.json").write_text(
        json.dumps({"valid_parent": True, "verdict": "keep", "reason": "explicit predictions"}) + "\n"
    )
    (run_dir / "meta_agent" / "predicted_fixes.json").write_text('["task-0"]\n')
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
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "library" / "record" / "jsonl.py"))

    fields = module["JsonlRecord"]().annotate({"genid": "1", "parent": "0"}, ctx).fields

    assert fields["predicted_fixes"] == ["task-0"]
    assert "verified_fixes" not in fields


def test_jsonl_record_without_gate_preserves_terminal_annotation(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    run_dir = workspace / "runs" / "operator-failed"
    (run_dir / "meta_agent").mkdir(parents=True)
    (run_dir / "meta_agent" / "rationale.md").write_text("meta-agent failed before gate\n")
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
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "library" / "record" / "jsonl.py"))

    fields = module["JsonlRecord"]().annotate({"genid": "1", "parent": "0"}, ctx).fields

    assert fields == {"note": "meta-agent failed before gate"}
