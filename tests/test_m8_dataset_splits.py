import json
import random
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import FIXTURE_SEEDS, run_evolve

from evolve.frozen.interfaces import OperatorContext
from evolve.splits import (
    build_manifest,
    load_manifest,
    select_dataset_tasks,
    selected_task_names,
    split_selection_digest,
)
from evolve.workspace import InitOptions, init_workspace


def _dataset(root: Path, count: int = 10) -> Path:
    root.mkdir()
    for index in range(count):
        task = root / f"task-{index}"
        task.mkdir()
        (task / "task.toml").write_text(f'version = "1.0"\nname = "task-{index}"\n')
    return root


def test_split_launcher_imports_in_a_fresh_process() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from evolve.splits import main"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_split_manifest_is_deterministic_disjoint_and_drift_checked(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "tasks")
    config = {"train": 0.5, "gate": 0.3, "sealed": 0.2, "seed": 7}

    first = build_manifest(dataset.as_posix(), config, base_dir=tmp_path, sampling="static", gate_limit=2)
    second = build_manifest(dataset.as_posix(), config, base_dir=tmp_path, sampling="static", gate_limit=2)

    assert first == second
    assert first["version"] == 2
    assert first["dataset_identity"]["source"] == "local"
    assert len(first["dataset_identity"]["digest"]) == 64
    assert set(first["task_digests"]) == {f"task-{index}" for index in range(10)}
    assert {name: len(first["tasks"][name]) for name in ("train", "gate", "sealed")} == {
        "train": 5,
        "gate": 3,
        "sealed": 2,
    }
    all_names = [set(first["tasks"][name]) for name in ("train", "gate", "sealed")]
    assert set.union(*all_names) == {f"task-{index}" for index in range(10)}
    assert not (all_names[0] & all_names[1] or all_names[0] & all_names[2] or all_names[1] & all_names[2])
    assert len(selected_task_names(first, "gate")) == 2
    assert split_selection_digest("gate", selected_task_names(first, "gate")) != split_selection_digest(
        "sealed", selected_task_names(first, "sealed")
    )

    manifest = tmp_path / "splits.json"
    manifest.write_text(json.dumps(first))
    selected, _ = select_dataset_tasks(manifest, dataset.as_posix(), "train", limit=3)
    assert selected == first["tasks"]["train"][:3]

    extra = dataset / "task-extra"
    extra.mkdir()
    (extra / "task.toml").write_text('version = "1.0"\n')
    with pytest.raises(RuntimeError, match="changed after init"):
        select_dataset_tasks(manifest, dataset.as_posix(), "train")


def test_local_split_rejects_selected_task_content_drift(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "tasks", count=4)
    manifest_payload = build_manifest(
        dataset.as_posix(),
        {"train": 0.5, "gate": 0.25, "sealed": 0.25, "seed": 2},
        base_dir=tmp_path,
        sampling="static",
        gate_limit=1,
    )
    manifest = tmp_path / "splits.json"
    manifest.write_text(json.dumps(manifest_payload))
    selected = manifest_payload["tasks"]["train"][0]
    (dataset / selected / "task.toml").write_text(f'version = "1.0"\nname = "{selected}"\nchanged = true\n')

    with pytest.raises(RuntimeError, match="dataset task content changed after init"):
        select_dataset_tasks(manifest, dataset.as_posix(), "train")


def test_version_one_split_manifest_remains_readable_as_legacy_unverified(tmp_path: Path) -> None:
    manifest_path = tmp_path / "splits.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "resolved": False,
                "tasks": {"train": [], "gate": [], "sealed": []},
            }
        )
    )

    manifest = load_manifest(manifest_path)

    assert manifest["version"] == 1
    assert manifest["identity_status"] == "legacy_unverified"


def test_init_dataset_option_freezes_local_harbor_tasks(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "tasks")
    workspace = tmp_path / "workspace"

    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "aevolve",
        "--dataset",
        str(dataset),
        env={"EVOLVE_HOME": str(tmp_path / "evolve-home")},
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((workspace / "evaluator" / "splits.json").read_text())
    assert manifest["resolved"] is True
    assert manifest["dataset"] == str(dataset)
    assert sum(len(manifest["tasks"][name]) for name in ("train", "gate", "sealed")) == 10
    pin = json.loads((workspace / "evaluator" / "dataset.pin").read_text())
    assert pin == {
        "digest": manifest["dataset_identity"]["digest"],
        "members": sorted(name for split in manifest["tasks"].values() for name in split),
        "resolved_reference": manifest["dataset_identity"]["resolved_reference"],
        "schema_version": 1,
        "source": "local",
    }


def test_init_full_task_scope_freezes_every_task_without_partition(tmp_path: Path, monkeypatch) -> None:
    dataset = _dataset(tmp_path / "tasks", count=4)
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("EVOLVE_RUNTIME_DIGEST", "sha256:test-runtime")
    monkeypatch.setattr(
        "evolve.workspace.default_config",
        lambda _recipe, name: {
            "experiment": {"id": name, "max_generations": 1, "children_per_gen": 1},
            "target": {"seed": str(FIXTURE_SEEDS / "dummy")},
            "surface": {"include": ["target/**"], "exclude": []},
            "operators": {
                "select": {"variant": "ahe_latest"},
                "rollout": {"variant": "harbor"},
                "meta_agent": {"variant": "ahe"},
                "gate": {"variant": "ahe_artifact_valid"},
                "record": {"variant": "jsonl"},
            },
            "evaluator": {
                "engine": "harbor",
                "dataset": str(dataset),
                "agent": "target.agent:HarborAgent",
                "task_scope": "full",
                "evaluation_split": "train",
                "sampling": "static",
                "tasks_per_round": 4,
                "k": 2,
                "n_concurrent": 4,
            },
        },
    )

    init_workspace(InitOptions(workspace=workspace, recipe="ahe", dataset=str(dataset)))

    manifest = json.loads((workspace / "evaluator" / "splits.json").read_text())
    assert manifest["ratios"] == {"train": 1.0, "gate": 0.0, "sealed": 0.0}
    assert manifest["tasks"]["train"] == [f"task-{index}" for index in range(4)]
    assert manifest["tasks"]["gate"] == []
    assert manifest["tasks"]["sealed"] == []
    config = (workspace / "evolve.yaml").read_text()
    assert "task_scope: full" in config
    assert "evaluation_split: train" in config


def test_split_rejects_invalid_ratios_and_datasets_too_small_for_isolation(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "tasks", count=2)
    with pytest.raises(ValueError, match="sum to 1.0"):
        build_manifest(
            dataset.as_posix(),
            {"train": 0.5, "gate": 0.5, "sealed": 0.5, "seed": 0},
            base_dir=tmp_path,
            sampling="static",
            gate_limit=1,
        )
    with pytest.raises(ValueError, match="too small"):
        build_manifest(
            dataset.as_posix(),
            {"train": 0.5, "gate": 0.4, "sealed": 0.1, "seed": 0},
            base_dir=tmp_path,
            sampling="static",
            gate_limit=1,
        )


def test_harbor_rollout_uses_only_frozen_train_task_names(tmp_path: Path, monkeypatch) -> None:
    from test_m7_harbor_rollout import _harbor_rollout_module

    module = _harbor_rollout_module()
    monkeypatch.delenv("EVOLVE_HARBOR_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    python_dir = tmp_path / "uv-python"
    monkeypatch.setenv("EVOLVE_UV_PYTHON_INSTALL_DIR", str(python_dir))
    checkout = tmp_path / "checkout"
    evaluator = checkout / "evaluator"
    evaluator.mkdir(parents=True)
    dataset = _dataset(tmp_path / "tasks")
    manifest = build_manifest(
        dataset.as_posix(),
        {"train": 0.5, "gate": 0.3, "sealed": 0.2, "seed": 3},
        base_dir=tmp_path,
        sampling="static",
        gate_limit=3,
    )
    (evaluator / "splits.json").write_text(json.dumps(manifest))
    (evaluator / "eval.env").write_text(
        f"EVOLVE_HARBOR_TASKS={dataset}\n"
        "EVOLVE_HARBOR_AGENT=target.agent:HarborAgent\n"
        f"EVOLVE_UV_CACHE_DIR={tmp_path / 'uv-cache'}\n"
    )
    (evaluator / "agent.env").write_text("UV_OFFLINE=1\nUV_PYTHON=3.12\n")
    captured: list[str] = []

    def fake_run(command, _checkout, log_path, env):
        captured.extend(command)
        assert env == {"LOCKED_RUNTIME": "1"}
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ok\n")
        return 0

    monkeypatch.setattr(
        module, "uv_run", lambda _workspace, *_command: (["uv", "run", "harbor"], {"LOCKED_RUNTIME": "1"})
    )
    monkeypatch.setattr(module, "_run_harbor", fake_run)
    monkeypatch.setattr(
        module,
        "collect_cases",
        lambda *_args, **_kwargs: [
            {"task_name": name, "reward": 1.0, "outcome": "passed"} for name in manifest["tasks"]["train"][:3]
        ],
    )
    context = OperatorContext(
        workspace=checkout,
        checkout=checkout,
        run_dir=checkout / "runs" / "gen-1",
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={
            "budget_tasks": 3,
            "jobs_dir": str(tmp_path / "jobs"),
            "environment": "custom.local:Environment",
            "environment_kwargs": {"workdir": "/workspace"},
        },
        rng=random.Random(0),
    )

    result = module.HarborRollout().rollout(checkout, context)

    included = [captured[index + 1] for index, value in enumerate(captured) if value == "--include-task-name"]
    assert included == manifest["tasks"]["train"][:3]
    assert f"EVOLVE_CANDIDATE_SOURCE={checkout / 'target'}" in captured
    mounts = json.loads(captured[captured.index("--mounts") + 1])
    assert mounts == [
        {
            "type": "bind",
            "source": str(tmp_path / "uv-cache"),
            "target": "/opt/evolve/uv/cache",
        },
        {
            "type": "bind",
            "source": str(python_dir),
            "target": "/installed-agent/uv-python",
        },
    ]
    assert captured.count("--mounts") == 1
    assert not set(included) & set(manifest["tasks"]["gate"] + manifest["tasks"]["sealed"])
    assert ("--ae", f"EVOLVE_CANDIDATE_SOURCE={checkout / 'target'}") in zip(captured, captured[1:], strict=False)
    assert ("--ae", "UV_CACHE_DIR=/opt/evolve/uv/cache") in zip(captured, captured[1:], strict=False)
    assert ("--ae", "UV_PYTHON_INSTALL_DIR=/installed-agent/uv-python") in zip(captured, captured[1:], strict=False)
    assert ("--ae", "UV_OFFLINE=1") in zip(captured, captured[1:], strict=False)
    assert ("--ae", "UV_PYTHON=3.12") in zip(captured, captured[1:], strict=False)
    assert ("--model", "openai/test-model") in zip(captured, captured[1:], strict=False)
    assert captured[captured.index("--env") + 1] == "custom.local:Environment"
    assert captured[captured.index("--environment-kwarg") + 1] == 'workdir="/workspace"'
    assert result.summary["split"] == "train"


def test_harbor_rollout_keeps_infra_tasks_without_outer_repair(tmp_path: Path, monkeypatch) -> None:
    from test_m7_harbor_rollout import _harbor_rollout_module

    module = _harbor_rollout_module()
    checkout = tmp_path / "checkout"
    evaluator = checkout / "evaluator"
    evaluator.mkdir(parents=True)
    dataset = _dataset(tmp_path / "tasks")
    manifest = build_manifest(
        dataset.as_posix(),
        {"train": 0.5, "gate": 0.3, "sealed": 0.2, "seed": 3},
        base_dir=tmp_path,
        sampling="static",
        gate_limit=3,
    )
    selected = manifest["tasks"]["train"][:2]
    (evaluator / "splits.json").write_text(json.dumps(manifest))
    (evaluator / "eval.env").write_text(
        f"EVOLVE_HARBOR_TASKS={dataset}\nEVOLVE_HARBOR_AGENT=target.agent:HarborAgent\n"
    )
    commands: list[list[str]] = []

    def fake_run(command, _checkout, log_path, _env):
        commands.append(command)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ok\n")
        return 0

    def fake_cases(jobs_dir, **_kwargs):
        return [
            {
                "task_name": f"terminal-bench/{selected[0]}",
                "reward": 1.0,
                "outcome": "passed",
                "result_path": str(jobs_dir / selected[0] / "result.json"),
            },
            {
                "task_name": f"terminal-bench/{selected[1]}",
                "reward": None,
                "outcome": "infra_error",
                "exception": {
                    "type": "VerifierTimeoutError",
                    "message": "verifier timed out",
                },
                "result_path": str(jobs_dir / selected[1] / "result.json"),
            },
        ]

    monkeypatch.setattr(module, "uv_run", lambda *_args: (["harbor"], {}))
    monkeypatch.setattr(module, "_run_harbor", fake_run)
    monkeypatch.setattr(module, "collect_cases", fake_cases)
    context = OperatorContext(
        workspace=checkout,
        checkout=checkout,
        run_dir=checkout / "runs" / "gen-1",
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={
            "budget_tasks": 2,
            "n_concurrent": 2,
            "jobs_dir": str(tmp_path / "jobs"),
        },
        rng=random.Random(0),
    )

    result = module.HarborRollout().rollout(checkout, context)

    assert len(commands) == 1
    initial_includes = [
        commands[0][index + 1] for index, value in enumerate(commands[0]) if value == "--include-task-name"
    ]
    assert initial_includes == selected

    cases = json.loads((context.run_dir / "rollout/cases.json").read_text())
    by_task = {case["task_name"]: case for case in cases}
    assert by_task[f"terminal-bench/{selected[0]}"]["outcome"] == "passed"
    infra = by_task[f"terminal-bench/{selected[1]}"]
    assert infra["outcome"] == "infra_error"
    assert infra["exception"]["type"] == "VerifierTimeoutError"
    assert not (context.run_dir / "rollout/repair").exists()
    assert result.summary["infra_errors"] == 1
    assert result.summary["infra_tasks"] == [f"terminal-bench/{selected[1]}"]
    assert result.summary["tasks_observed"] == 2


def test_harbor_rollout_exact_task_replay_is_limited_to_frozen_train_split(tmp_path: Path, monkeypatch) -> None:
    from test_m7_harbor_rollout import _harbor_rollout_module

    module = _harbor_rollout_module()
    monkeypatch.setattr(
        module,
        "select_dataset_tasks",
        lambda *_args, **_kwargs: (["train-a", "train-b", "train-c"], "hash"),
    )

    selected = module._select_train_tasks(tmp_path / "splits.json", "dataset", 1, ["train-c", "train-a"])

    assert selected == ["train-c", "train-a"]
    assert module._select_train_tasks(
        tmp_path / "splits.json",
        "dataset",
        1,
        ["terminal-bench/train-c", "terminal-bench/train-a"],
    ) == ["train-c", "train-a"]
    with pytest.raises(ValueError, match="frozen train split"):
        module._select_train_tasks(tmp_path / "splits.json", "dataset", 1, ["gate-a"])
    with pytest.raises(ValueError, match="frozen train split"):
        module._select_train_tasks(
            tmp_path / "splits.json",
            "dataset",
            1,
            ["terminal-bench/gate-a"],
        )
    with pytest.raises(ValueError, match="duplicates"):
        module._select_train_tasks(
            tmp_path / "splits.json",
            "dataset",
            1,
            ["train-c", "terminal-bench/train-c"],
        )


def test_harbor_rollout_can_shuffle_train_minibatches_by_generation(tmp_path: Path, monkeypatch) -> None:
    from test_m7_harbor_rollout import _harbor_rollout_module

    module = _harbor_rollout_module()
    names = [f"train-{index}" for index in range(20)]
    monkeypatch.setattr(module, "select_dataset_tasks", lambda *_args, **_kwargs: (names, "hash"))

    first = module._select_train_tasks(
        tmp_path / "splits.json",
        "dataset",
        5,
        sampling="generation_shuffle",
        sampling_key="0:1",
    )
    second = module._select_train_tasks(
        tmp_path / "splits.json",
        "dataset",
        5,
        sampling="generation_shuffle",
        sampling_key="0:2",
    )

    assert first != second
    assert len(first) == len(set(first)) == 5
    assert set(first) <= set(names)
