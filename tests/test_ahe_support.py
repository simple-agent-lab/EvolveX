import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ahe_support", ROOT / "library" / "ahe_support.py")
assert SPEC is not None and SPEC.loader is not None
AHE_SUPPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AHE_SUPPORT)

compare_states = AHE_SUPPORT.compare_states
evaluate_manifest = AHE_SUPPORT.evaluate_manifest
select_debugger_tasks = AHE_SUPPORT.select_debugger_tasks
task_states = AHE_SUPPORT.task_states
validate_change_manifest = AHE_SUPPORT.validate_change_manifest
verify_relative_hash = AHE_SUPPORT.verify_relative_hash


def make_vector(outcomes: dict[str, list[int | None]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "tasks": {
            task_id: {
                "trials": [
                    {
                        "trial": index,
                        "status": "complete" if reward is not None else "infra_failed",
                        "reward": float(reward) if reward is not None else None,
                    }
                    for index, reward in enumerate(rewards)
                ]
            }
            for task_id, rewards in outcomes.items()
        },
    }


def test_task_states_require_two_complete_trials() -> None:
    vector = make_vector({"pass": [1, 1], "partial": [1, 0], "fail": [0, 0], "unknown": [1, None]})

    assert task_states(vector) == {
        "fail": "fail",
        "partial": "partial",
        "pass": "pass",
        "unknown": "unknown",
    }


def test_compare_states_orders_improvements_and_regressions() -> None:
    assert compare_states(
        {"a": "fail", "b": "pass", "c": "unknown"},
        {"a": "pass", "b": "partial", "c": "fail"},
    ) == {
        "improved": ["a"],
        "regressed": ["b"],
        "unchanged": [],
        "unknown": ["c"],
    }


def test_manifest_attribution_marks_harmful_change() -> None:
    result = evaluate_manifest(
        {"changes": [{"id": "chg-1", "predicted_fixes": ["a"], "risk_tasks": ["b"]}]},
        make_vector({"a": [0, 0], "b": [1, 1]}),
        make_vector({"a": [0, 0], "b": [0, 0]}),
    )

    assert result["changes"][0]["verdict"] == "HARMFUL"
    assert result["changes"][0]["recommendation"] == "ROLLBACK_PIVOT"
    assert result["changes"][0]["realized_risks"] == ["b"]


def test_manifest_attribution_verifies_only_reliable_improvement_to_pass() -> None:
    result = evaluate_manifest(
        {
            "changes": [
                {
                    "id": "chg-1",
                    "predicted_fixes": ["fail-to-pass", "partial-to-pass", "already-pass", "fail-to-partial"],
                    "risk_tasks": [],
                }
            ]
        },
        make_vector(
            {
                "fail-to-pass": [0, 0],
                "partial-to-pass": [1, 0],
                "already-pass": [1, 1],
                "fail-to-partial": [0, 0],
            }
        ),
        make_vector(
            {
                "fail-to-pass": [1, 1],
                "partial-to-pass": [1, 1],
                "already-pass": [1, 1],
                "fail-to-partial": [1, 0],
            }
        ),
    )

    change = result["changes"][0]
    assert change["verified_fixes"] == ["fail-to-pass", "partial-to-pass"]
    assert change["still_failing_predictions"] == ["already-pass", "fail-to-partial"]
    assert change["verdict"] == "PARTIALLY_EFFECTIVE"
    assert change["recommendation"] == "REVISE"


def test_manifest_attribution_treats_every_reliable_regression_as_harm() -> None:
    result = evaluate_manifest(
        {"changes": [{"id": "chg-1", "predicted_fixes": ["fixed"], "risk_tasks": []}]},
        make_vector({"fixed": [0, 0], "unexpected": [1, 1]}),
        make_vector({"fixed": [1, 1], "unexpected": [1, 0]}),
    )

    change = result["changes"][0]
    assert change["verified_fixes"] == ["fixed"]
    assert change["unexpected_regressions"] == ["unexpected"]
    assert change["verdict"] == "MIXED"
    assert change["recommendation"] == "ROLLBACK_PIVOT"


def test_select_debugger_tasks_uses_seeded_sorted_success_controls() -> None:
    selection = select_debugger_tasks(
        {"a": "fail", "b": "pass", "c": "pass", "d": "pass", "e": "partial", "risk-pass": "pass"},
        {"improved": [], "regressed": ["e"], "unchanged": [], "unknown": []},
        ["a", "risk-pass"],
        successful_controls=2,
        seed=7,
        generation=3,
    )

    assert selection == {
        "failure": ["a", "e"],
        "regression": ["e"],
        "risk": ["a", "risk-pass"],
        "control": ["d", "b"],
    }


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "generation": 2,
        "parent": "1",
        "decision": "revise",
        "changes": [
            {
                "id": "chg-1",
                "type": "improvement",
                "files": ["target/agent.py"],
                "failure_evidence": [{"task_id": "task-1", "report": "analysis/detail/task-1.md"}],
                "root_cause": "The tool call is malformed.",
                "targeted_fix": "Normalize the tool arguments.",
                "predicted_fixes": ["task-1"],
                "risk_tasks": [],
                "component_level": "tool",
            }
        ],
        "validation": {"status": "passed", "commands": ["pytest -q"]},
    }


def _validate(manifest: object, run_dir: Path) -> dict[str, object]:
    return validate_change_manifest(
        manifest,
        generation="2",
        parent="1",
        changed_paths=["target/agent.py"],
        run_dir=run_dir,
        surface_report={"ok": True, "mutated": ["target/agent.py"], "violations": []},
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda entry: entry.pop("risk_tasks"), "risk_tasks"),
        (lambda entry: entry.update(failure_evidence=[]), "failure_evidence"),
        (lambda entry: entry.update(files=["../agent.py"]), "unsafe path"),
        (lambda entry: entry.update(files=[]), "changed paths"),
        (lambda entry: entry.update(files=["target/agent.py", "target/agent.py"]), "exactly once"),
    ],
)
def test_validate_change_manifest_rejects_invalid_evidence_and_coverage(tmp_path: Path, mutate, message: str) -> None:
    run_dir = tmp_path / "run"
    report = run_dir / "analysis" / "detail" / "task-1.md"
    report.parent.mkdir(parents=True)
    report.write_text("evidence\n")
    manifest = _manifest()
    entry = manifest["changes"][0]
    assert isinstance(entry, dict)
    mutate(entry)

    with pytest.raises(ValueError, match=message):
        _validate(manifest, run_dir)


def test_validate_change_manifest_rejects_missing_evidence_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="evidence report"):
        _validate(_manifest(), tmp_path / "run")


def test_validate_change_manifest_rejects_surface_mismatch(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    report = run_dir / "analysis" / "detail" / "task-1.md"
    report.parent.mkdir(parents=True)
    report.write_text("evidence\n")

    with pytest.raises(ValueError, match="surface"):
        validate_change_manifest(
            _manifest(),
            generation="2",
            parent="1",
            changed_paths=["target/agent.py"],
            run_dir=run_dir,
            surface_report={"ok": False, "mutated": ["target/agent.py"], "violations": ["target/agent.py"]},
        )


def test_verify_relative_hash_requires_workspace_relative_matching_file(tmp_path: Path) -> None:
    artifact = tmp_path / "runs" / "gen-2" / "eval" / "evaluation_artifacts.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}\n")

    assert (
        verify_relative_hash(
            tmp_path,
            {
                "path": "runs/gen-2/eval/evaluation_artifacts.json",
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            },
        )
        == artifact
    )

    with pytest.raises(ValueError, match="unsafe path"):
        verify_relative_hash(tmp_path, {"path": "../outside", "sha256": "0" * 64})
