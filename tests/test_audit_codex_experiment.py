from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "audit_codex_experiment.py"
APPROVED_TASKS = ["train-alpha", "train-beta", "train-gamma"]


def _git(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(workspace), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _write_config(
    workspace: Path,
    *,
    train: list[str],
    anchor_final: bool,
) -> None:
    config = {
        "experiment": {
            "id": "codex-audit-fixture",
            "max_generations": 2,
            "children_per_gen": 1,
            "mode": "driver",
            "seed": 0,
        },
        "target": {"seed": "builtin-codex"},
        "surface": {"include": ["target/**"], "exclude": []},
        "operators": {
            "meta_agent": {
                "agent": "codex",
                "model": "gpt-5.4",
                "prompt_path": "target/prompt.md",
                "skills_dir": "target/skills",
                "editable_roots": ["target"],
            }
        },
        "evaluator": {
            "engine": "harbor",
            "model": "gpt-5.4",
            "dataset": "/datasets/public-benchmark",
            "agent": "target.agent:HarborAgent",
            "agent_env": {},
            "evaluation_split": "train",
            "sampling": "static",
            "tasks_per_round": len(train),
            "task_names": train,
            "anchor": {"final": anchor_final, "every_rounds": 0},
        },
    }
    (workspace / "evolve.yaml").write_text(yaml.safe_dump(config, sort_keys=False))


def _write_split_files(
    workspace: Path,
    *,
    train: list[str],
    gate: list[str],
    sealed: list[str],
) -> None:
    evaluator = workspace / "evaluator"
    tasks_dir = evaluator / "tasks"
    tasks_dir.mkdir(parents=True)
    manifest = {
        "version": 1,
        "resolved": True,
        "counts": {
            "train": len(train),
            "gate": len(gate),
            "sealed": len(sealed),
        },
        "tasks": {"train": train, "gate": gate, "sealed": sealed},
        "digests": {
            split: hashlib.sha256(json.dumps(sorted(names), separators=(",", ":")).encode()).hexdigest()
            for split, names in {
                "train": train,
                "gate": gate,
                "sealed": sealed,
            }.items()
        },
    }
    (evaluator / "splits.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (tasks_dir / "train.txt").write_text("".join(f"{task}\n" for task in train))
    (tasks_dir / "sealed.txt").write_text("".join(f"{task}\n" for task in sealed))
    (evaluator / "agent.kwargs").write_text("reasoning_effort=high\n")
    (evaluator / "eval.env").write_text(
        "EVOLVE_HARBOR_AGENT=target.agent:HarborAgent\n"
        "EVOLVE_HARBOR_CODEX_SUBSCRIPTION=1\n"
        f"EVOLVE_HARBOR_EXPECTED_TRIALS={len(train)}\n"
        "EVOLVE_HARBOR_MODEL=gpt-5.4\n"
    )


def _prepared_workspace(
    tmp_path: Path,
    *,
    train: list[str] | None = None,
    anchor_final: bool = True,
) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    train = train or ["train-one", "train-two", "train-three", "train-four"]
    _write_config(workspace, train=train, anchor_final=anchor_final)
    _write_split_files(
        workspace,
        train=train,
        gate=["private-gate-one", "private-gate-two"],
        sealed=["private-sealed-one", "private-sealed-two"],
    )
    if not anchor_final:
        (workspace / "evaluator" / "smoke-task-names.txt").write_text("".join(f"{task}\n" for task in train))
    return workspace


def _run_audit(
    workspace: Path,
    mode: str,
    *extra: str,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    result = subprocess.run(
        [
            sys.executable,
            str(AUDIT),
            str(workspace),
            "--mode",
            mode,
            *extra,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    report = json.loads(result.stdout)
    return result, report


def _assert_failure(
    workspace: Path,
    mode: str = "prepared",
    *extra: str,
    contains: str,
) -> dict[str, object]:
    result, report = _run_audit(workspace, mode, *extra)
    assert result.returncode != 0
    assert report["ok"] is False
    assert contains.lower() in "\n".join(report["errors"]).lower()
    return report


def test_prepared_workspace_passes_codex_contract(tmp_path: Path) -> None:
    workspace = _prepared_workspace(tmp_path)

    result, report = _run_audit(workspace, "prepared")

    assert result.returncode == 0, result.stderr
    assert set(report) == {
        "ok",
        "errors",
        "experiment",
        "tasks",
        "lineage",
        "reasoning",
        "anchor",
    }
    assert report["ok"] is True
    assert report["errors"] == []
    assert report["reasoning"] == {"reasoning_effort": "high"}
    assert report["anchor"] == {"final": True, "every_rounds": 0}
    assert report["tasks"]["train_count"] == 4
    assert report["tasks"]["sealed_count"] == 2
    assert report["tasks"]["train_names"] == [
        "train-one",
        "train-two",
        "train-three",
        "train-four",
    ]


def test_prepared_workspace_rejects_miniswe_evaluator_agent(
    tmp_path: Path,
) -> None:
    workspace = _prepared_workspace(tmp_path)
    config_path = workspace / "evolve.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["evaluator"]["agent"] = "evolve.integrations.harbor.miniswe_candidate:MiniSweSourceAgent"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))

    _assert_failure(workspace, contains="HarborAgent")


def test_prepared_workspace_rejects_missing_protected_reasoning(
    tmp_path: Path,
) -> None:
    workspace = _prepared_workspace(tmp_path)
    (workspace / "evaluator" / "agent.kwargs").unlink()

    _assert_failure(workspace, contains="reasoning_effort")


def test_prepared_workspace_rejects_non_codex_model(tmp_path: Path) -> None:
    workspace = _prepared_workspace(tmp_path)
    config_path = workspace / "evolve.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["evaluator"]["model"] = "openai/gpt-5.4-2026-03-05"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))

    _assert_failure(workspace, contains="evaluator.model")


def test_prepared_workspace_rejects_non_codex_meta_agent_profile(
    tmp_path: Path,
) -> None:
    workspace = _prepared_workspace(tmp_path)
    config_path = workspace / "evolve.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["operators"]["meta_agent"]["model"] = "openai/gpt-5.4-2026-03-05"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))

    _assert_failure(workspace, contains="meta_agent.model")


def test_prepared_workspace_rejects_split_digest_mismatch(
    tmp_path: Path,
) -> None:
    workspace = _prepared_workspace(tmp_path)
    manifest_path = workspace / "evaluator" / "splits.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["digests"]["train"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))

    _assert_failure(workspace, contains="digests.train")


def test_prepared_workspace_rejects_task_file_membership_mismatch(
    tmp_path: Path,
) -> None:
    workspace = _prepared_workspace(tmp_path)
    (workspace / "evaluator" / "tasks" / "train.txt").write_text("train-one\ntrain-two\nwrong-task\ntrain-four\n")

    _assert_failure(workspace, contains="train.txt")


def test_prepared_smoke_requires_disabled_anchor_and_three_tasks(
    tmp_path: Path,
) -> None:
    workspace = _prepared_workspace(
        tmp_path,
        train=APPROVED_TASKS,
        anchor_final=False,
    )

    result, report = _run_audit(
        workspace,
        "prepared",
        "--expected-anchor",
        "none",
    )

    assert result.returncode == 0, result.stderr
    assert report["ok"] is True
    assert report["tasks"]["train_count"] == 3
    assert report["tasks"]["train_names"] == APPROVED_TASKS
    assert report["anchor"] == {"final": False, "every_rounds": 0}


def test_prepared_smoke_rejects_nonzero_anchor_cadence(tmp_path: Path) -> None:
    workspace = _prepared_workspace(
        tmp_path,
        train=APPROVED_TASKS,
        anchor_final=False,
    )
    config_path = workspace / "evolve.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["evaluator"]["anchor"]["every_rounds"] = 1
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))

    _assert_failure(
        workspace,
        "prepared",
        "--expected-anchor",
        "none",
        contains="every_rounds",
    )


def test_prepared_smoke_rejects_unapproved_train_membership(
    tmp_path: Path,
) -> None:
    workspace = _prepared_workspace(
        tmp_path,
        train=APPROVED_TASKS,
        anchor_final=False,
    )
    (workspace / "evaluator" / "smoke-task-names.txt").write_text("train-alpha\ntrain-beta\nunapproved-task\n")

    _assert_failure(
        workspace,
        "prepared",
        "--expected-anchor",
        "none",
        contains="smoke-task-names.txt",
    )


def _write_trial_config(
    workspace: Path,
    generation: int,
    *,
    candidate_commit: str,
    task: str,
    attempt: int = 1,
    purpose: str = "candidate",
    reasoning_effort: str = "high",
    trial_suffix: str = "",
) -> None:
    trial = (
        workspace
        / "runs"
        / "evaluations"
        / purpose
        / f"gen-{generation}"
        / f"candidate-{candidate_commit}"
        / f"attempt-{attempt}"
        / "jobs"
        / f"job-{generation}"
        / f"trial-{task}{trial_suffix}"
    )
    trial.mkdir(parents=True)
    (trial / "config.json").write_text(
        json.dumps(
            {
                "task": {"path": f"/dataset/{task}"},
                "agent": {
                    "name": "target.agent:HarborAgent",
                    "kwargs": {"reasoning_effort": reasoning_effort},
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _smoke_workspace(tmp_path: Path) -> Path:
    workspace = _prepared_workspace(
        tmp_path,
        train=APPROVED_TASKS,
        anchor_final=False,
    )
    target = workspace / "target"
    target.mkdir()
    (target / "prompt.md").write_text("generation zero\n")
    _git(workspace, "init", "-q")
    _git(workspace, "config", "user.name", "Audit Fixture")
    _git(workspace, "config", "user.email", "audit@example.invalid")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-qm", "generation zero")
    _git(workspace, "tag", "gen/0")
    for generation in (1, 2):
        (target / "prompt.md").write_text(f"generation {generation}\n")
        _git(workspace, "add", "target/prompt.md")
        _git(workspace, "commit", "-qm", f"generation {generation}")
        _git(workspace, "tag", f"gen/{generation}")

    events = []
    for generation in range(3):
        candidate_commit = _git(
            workspace,
            "rev-parse",
            f"gen/{generation}^{{commit}}",
        )
        events.append(
            {
                "_evolve_mechanism_eval": True,
                "purpose": "candidate",
                "generation": str(generation),
                "genid": str(generation),
                "tag": f"gen/{generation}",
                "candidate_commit": candidate_commit,
                "attempt": 1,
                "parent": None if generation == 0 else str(generation - 1),
                "status": "complete",
                "selection_eligible": True,
                "expected_trials": 3,
                "task_set_members": APPROVED_TASKS,
                "task_vector": {
                    "schema_version": 1,
                    "tasks": {
                        task: {
                            "trials": [
                                {
                                    "trial": 0,
                                    "status": "benchmark_complete",
                                    "reward": 1.0,
                                    "owner": "benchmark",
                                }
                            ]
                        }
                        for task in APPROVED_TASKS
                    },
                },
            }
        )
        for task in APPROVED_TASKS:
            _write_trial_config(
                workspace,
                generation,
                candidate_commit=candidate_commit,
                task=task,
            )
    (workspace / "archive.jsonl").write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events))
    return workspace


def _rewrite_events(workspace: Path, transform) -> None:
    archive = workspace / "archive.jsonl"
    events = [json.loads(line) for line in archive.read_text().splitlines() if line.strip()]
    transformed = transform(events)
    archive.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in transformed))


def test_smoke_lineage_through_generation_passes(tmp_path: Path) -> None:
    workspace = _smoke_workspace(tmp_path)

    result, report = _run_audit(
        workspace,
        "smoke",
        "--through-generation",
        "2",
    )

    assert result.returncode == 0, result.stderr
    assert report["ok"] is True
    assert report["lineage"]["through_generation"] == 2
    assert report["lineage"]["generations"] == [0, 1, 2]
    assert report["lineage"]["complete_evaluations"] == 3
    assert report["lineage"]["harbor_config_count"] == 9
    assert report["lineage"]["surface_violations"] == []
    assert report["lineage"]["privacy_leaks"] == []
    assert report["reasoning"] == {"reasoning_effort": "high"}


def test_smoke_accepts_real_genesis_evaluation_for_generation_zero(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)
    candidate_root = workspace / "runs" / "evaluations" / "candidate" / "gen-0"
    genesis_root = workspace / "runs" / "evaluations" / "genesis" / "gen-0"
    genesis_root.parent.mkdir()
    candidate_root.rename(genesis_root)

    def change(events):
        events[0]["purpose"] = "genesis"
        return events

    _rewrite_events(workspace, change)

    result, report = _run_audit(
        workspace,
        "smoke",
        "--through-generation",
        "2",
    )

    assert result.returncode == 0, result.stderr
    assert report["ok"] is True
    assert report["lineage"]["complete_evaluations"] == 3


def test_smoke_rejects_genesis_evaluation_after_generation_zero(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        events[1]["purpose"] = "genesis"
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="generation 1",
    )


def test_smoke_rejects_candidate_commit_that_does_not_match_tag(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        events[1]["candidate_commit"] = events[0]["candidate_commit"]
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="candidate_commit",
    )


@pytest.mark.parametrize(
    "field",
    ["tag", "genid", "candidate_commit", "attempt", "parent"],
)
def test_smoke_rejects_missing_canonical_linkage_field(
    tmp_path: Path,
    field: str,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        events[1].pop(field)
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains=field,
    )


def test_smoke_rejects_missing_generation_zero_parent(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        events[0].pop("parent")
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="parent",
    )


def test_smoke_rejects_nonnull_generation_zero_parent(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        events[0]["parent"] = "0"
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="parent",
    )


def test_smoke_rejects_self_parent_without_empty_diff_bypass(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        events[1]["parent"] = "1"
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="parent",
    )


def test_smoke_rejects_parent_that_is_not_candidate_commit_parent(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        events[2]["parent"] = "0"
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="commit parent",
    )


def test_smoke_ignores_unrelated_good_config_when_canonical_configs_are_bad(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)
    canonical_root = workspace / "runs" / "evaluations" / "candidate" / "gen-1"
    for config_path in canonical_root.rglob("config.json"):
        config = json.loads(config_path.read_text())
        config.pop("agent")
        config_path.write_text(json.dumps(config))
    for task in APPROVED_TASKS:
        _write_trial_config(
            workspace,
            1,
            candidate_commit="unrelated",
            task=task,
        )

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="canonical",
    )


def test_smoke_rejects_competing_candidate_and_genesis_events_at_zero(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        competing = {**events[0], "purpose": "genesis"}
        return [*events, competing]

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="exactly one",
    )


def test_smoke_rejects_duplicate_complete_candidates_for_generation(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        duplicate = {
            **events[1],
            "candidate_commit": events[0]["candidate_commit"],
        }
        return [*events, duplicate]

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="exactly one",
    )


def test_smoke_rejects_duplicate_complete_attempts_for_generation(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        duplicate = {**events[1], "attempt": 2}
        return [*events, duplicate]

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="exactly one",
    )


def test_smoke_rejects_missing_task_vector(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        events[1].pop("task_vector")
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="task_vector",
    )


@pytest.mark.parametrize(
    ("replacement", "expected_error"),
    [
        ({}, "trial"),
        (
            {
                "trial": 0,
                "status": "infrastructure_failed",
                "reward": None,
                "owner": "infrastructure",
            },
            "scoreable",
        ),
        (
            {
                "trial": 0,
                "status": "benchmark_complete",
                "reward": None,
                "owner": "benchmark",
            },
            "scoreable",
        ),
    ],
)
def test_smoke_rejects_incomplete_failed_or_unscoreable_vector_trial(
    tmp_path: Path,
    replacement: dict[str, object],
    expected_error: str,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        events[1]["task_vector"]["tasks"][APPROVED_TASKS[0]]["trials"] = [replacement]
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains=expected_error,
    )


@pytest.mark.parametrize(
    ("field", "value", "owner"),
    [
        ("exception_type", "RuntimeError", "infrastructure"),
        ("exception_message", "candidate execution failed", "candidate"),
    ],
)
def test_smoke_rejects_exception_bearing_benchmark_complete_trial(
    tmp_path: Path,
    field: str,
    value: str,
    owner: str,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        trial = events[1]["task_vector"]["tasks"][APPROVED_TASKS[0]]["trials"][0]
        trial["owner"] = owner
        trial[field] = value
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="scoreable",
    )


def test_smoke_rejects_missing_vector_trial_number(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        del events[1]["task_vector"]["tasks"][APPROVED_TASKS[0]]["trials"][0]["trial"]
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="trial number",
    )


def test_smoke_rejects_duplicate_vector_trial_number(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        tasks = events[1]["task_vector"]["tasks"]
        tasks[APPROVED_TASKS[0]]["trials"].append(dict(tasks[APPROVED_TASKS[0]]["trials"][0]))
        del tasks[APPROVED_TASKS[2]]
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="duplicate trial number",
    )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong"])
def test_smoke_rejects_missing_duplicate_or_wrong_vector_task(
    tmp_path: Path,
    mutation: str,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        tasks = events[1]["task_vector"]["tasks"]
        removed = tasks.pop(APPROVED_TASKS[2])
        if mutation == "duplicate":
            duplicate = dict(tasks[APPROVED_TASKS[0]]["trials"][0])
            duplicate["trial"] = 1
            tasks[APPROVED_TASKS[0]]["trials"].append(duplicate)
        elif mutation == "wrong":
            tasks["private-gate-one"] = removed
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="approved task",
    )


def test_smoke_rejects_config_and_task_vector_identity_mismatch(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)
    generation_root = workspace / "runs" / "evaluations" / "candidate" / "gen-1"
    config_path = next(
        path
        for path in generation_root.rglob("config.json")
        if json.loads(path.read_text())["task"]["path"].endswith(APPROVED_TASKS[2])
    )
    config = json.loads(config_path.read_text())
    config["task"]["path"] = "/dataset/config-only-task"
    config_path.write_text(json.dumps(config))

    def change(events):
        tasks = events[1]["task_vector"]["tasks"]
        tasks["vector-only-task"] = tasks.pop(APPROVED_TASKS[2])
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="must match task_vector",
    )


def test_smoke_rejects_missing_generation_tag(tmp_path: Path) -> None:
    workspace = _smoke_workspace(tmp_path)
    _git(workspace, "tag", "-d", "gen/1")

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="gen/1",
    )


def test_smoke_rejects_expected_trials_other_than_three(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        events[1]["expected_trials"] = 2
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="expected_trials",
    )


def test_smoke_rejects_private_task_in_evaluation_members(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        events[2]["task_set_members"] = [
            APPROVED_TASKS[0],
            APPROVED_TASKS[1],
            "private-gate-one",
        ]
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="task_set_members",
    )


def test_smoke_returns_json_for_malformed_task_members(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        events[2]["task_set_members"] = [
            APPROVED_TASKS[0],
            APPROVED_TASKS[1],
            {"not": "a task identifier"},
        ]
        return events

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="task_set_members",
    )


def test_smoke_rejects_gate_or_sealed_identifier_in_feedback_text(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)
    feedback = workspace / "runs" / "gen-2" / "feedback"
    feedback.mkdir(parents=True)
    (feedback / "selected.md").write_text("The evaluator exposed private-sealed-one to the mutator.\n")

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="private task identifier",
    )


def test_smoke_rejects_anchor_event(tmp_path: Path) -> None:
    workspace = _smoke_workspace(tmp_path)

    def change(events):
        return [
            *events,
            {
                "_evolve_mechanism_eval": True,
                "purpose": "anchor",
                "kind": "anchor",
                "generation": "2",
                "genid": "2",
                "tag": "gen/2",
                "status": "complete",
            },
        ]

    _rewrite_events(workspace, change)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="anchor event",
    )


def test_smoke_rejects_effective_reasoning_other_than_high(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)
    config_path = next((workspace / "runs" / "evaluations" / "candidate" / "gen-1").rglob("config.json"))
    config = json.loads(config_path.read_text())
    config["agent"]["kwargs"]["reasoning_effort"] = "medium"
    config_path.write_text(json.dumps(config))

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="persisted Harbor",
    )


def test_smoke_rejects_missing_actual_harbor_trial(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)
    generation_root = workspace / "runs" / "evaluations" / "candidate" / "gen-1"
    next(generation_root.rglob("config.json")).unlink()

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="exactly three persisted Harbor trials",
    )


def test_smoke_rejects_duplicate_actual_harbor_trial(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)
    commit = _git(workspace, "rev-parse", "gen/1^{commit}")
    _write_trial_config(
        workspace,
        1,
        candidate_commit=commit,
        task=APPROVED_TASKS[0],
        trial_suffix="-duplicate",
    )

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="exactly three persisted Harbor trials",
    )


def test_smoke_rejects_wrong_actual_harbor_trial_task(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)
    generation_root = workspace / "runs" / "evaluations" / "candidate" / "gen-1"
    config_path = next(generation_root.rglob("config.json"))
    config = json.loads(config_path.read_text())
    config["task"]["path"] = "/dataset/private-gate-one"
    config_path.write_text(json.dumps(config))

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="approved task identities",
    )


def test_smoke_rejects_mutation_outside_configured_surface(
    tmp_path: Path,
) -> None:
    workspace = _smoke_workspace(tmp_path)
    (workspace / "README.md").write_text("outside surface\n")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "--amend", "--no-edit", "-q")
    _git(workspace, "tag", "-f", "gen/2")
    new_commit = _git(workspace, "rev-parse", "gen/2^{commit}")
    generation_root = workspace / "runs" / "evaluations" / "candidate" / "gen-2"
    old_candidate_root = next(generation_root.glob("candidate-*"))
    old_candidate_root.rename(generation_root / f"candidate-{new_commit}")

    def relink(events):
        events[2]["candidate_commit"] = new_commit
        return events

    _rewrite_events(workspace, relink)

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains="surface",
    )


@pytest.mark.parametrize(
    ("split", "malformed"),
    [
        ("gate", "not-a-list"),
        ("sealed", None),
    ],
)
def test_smoke_returns_json_for_malformed_private_split_types(
    tmp_path: Path,
    split: str,
    malformed: object,
) -> None:
    workspace = _smoke_workspace(tmp_path)
    manifest_path = workspace / "evaluator" / "splits.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["tasks"][split] = malformed
    manifest_path.write_text(json.dumps(manifest))

    _assert_failure(
        workspace,
        "smoke",
        "--through-generation",
        "2",
        contains=f"tasks.{split}",
    )


def test_report_is_deterministic_and_does_not_emit_environment_values(
    tmp_path: Path,
) -> None:
    workspace = _prepared_workspace(tmp_path)
    secret = "audit-secret-must-not-appear"
    evaluator = workspace / "evaluator"
    (evaluator / "eval.env").write_text(
        (evaluator / "eval.env").read_text()
        + f"OPENAI_API_KEY={secret}\n"
        + f"HTTPS_PROXY=http://user:{secret}@proxy.invalid\n"
    )
    (workspace / "auth.json").write_text(json.dumps({"tokens": {"access_token": secret}}))
    output = tmp_path / "audit.json"

    first = subprocess.run(
        [
            sys.executable,
            str(AUDIT),
            str(workspace),
            "--mode",
            "prepared",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "OPENAI_API_KEY": secret},
    )
    first_text = output.read_text()
    second = subprocess.run(
        [
            sys.executable,
            str(AUDIT),
            str(workspace),
            "--mode",
            "prepared",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "OPENAI_API_KEY": "different-secret"},
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == ""
    assert second.stdout == ""
    assert output.read_text() == first_text
    assert secret not in first_text
    assert "different-secret" not in first_text


def test_smoke_requires_through_generation(tmp_path: Path) -> None:
    workspace = _smoke_workspace(tmp_path)

    result = subprocess.run(
        [sys.executable, str(AUDIT), str(workspace), "--mode", "smoke"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--through-generation" in result.stderr
