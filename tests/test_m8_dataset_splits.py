import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import init_workspace, rows_by_genid, run_evolve

from evolve.feedback import write_feedback_bundle
from evolve.frozen.interfaces import OperatorContext
from evolve.splits import build_manifest, select_dataset_tasks, selected_task_names, task_set_hash


def _dataset(root: Path, count: int = 10) -> Path:
    root.mkdir()
    for index in range(count):
        task = root / f"task-{index}"
        task.mkdir()
        (task / "task.toml").write_text(f'version = "1.0"\nname = "task-{index}"\n')
    return root


def test_split_manifest_is_deterministic_disjoint_and_drift_checked(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "tasks")
    config = {"train": 0.5, "gate": 0.3, "sealed": 0.2, "seed": 7}

    first = build_manifest(dataset.as_posix(), config, base_dir=tmp_path, sampling="static", gate_limit=2)
    second = build_manifest(dataset.as_posix(), config, base_dir=tmp_path, sampling="static", gate_limit=2)

    assert first == second
    assert {name: len(first["tasks"][name]) for name in ("train", "gate", "sealed")} == {
        "train": 5,
        "gate": 3,
        "sealed": 2,
    }
    all_names = [set(first["tasks"][name]) for name in ("train", "gate", "sealed")]
    assert set.union(*all_names) == {f"task-{index}" for index in range(10)}
    assert not (all_names[0] & all_names[1] or all_names[0] & all_names[2] or all_names[1] & all_names[2])
    assert len(selected_task_names(first, "gate")) == 2
    assert task_set_hash("gate", selected_task_names(first, "gate")) != task_set_hash(
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


def test_init_dataset_option_freezes_local_harbor_tasks(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "tasks")
    workspace = tmp_path / "workspace"

    result = run_evolve(
        "init", str(workspace), "--dataset", str(dataset), env={"EVOLVE_HOME": str(tmp_path / "evolve-home")}
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((workspace / "evaluator" / "splits.json").read_text())
    assert manifest["resolved"] is True
    assert manifest["dataset"] == str(dataset)
    assert sum(len(manifest["tasks"][name]) for name in ("train", "gate", "sealed")) == 10


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
        f"EVOLVE_HARBOR_TASKS={dataset}\nEVOLVE_HARBOR_AGENT=target.agent:HarborAgent\n"
    )
    captured: list[str] = []

    def fake_run(command, _checkout, log_path):
        captured.extend(command)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ok\n")
        return 0

    monkeypatch.setattr(module.shutil, "which", lambda _name: "/usr/bin/harbor")
    monkeypatch.setattr(module, "_run_harbor", fake_run)
    monkeypatch.setattr(module, "_collect_cases", lambda *_args, **_kwargs: [{"reward": 1.0, "outcome": "passed"}])
    monkeypatch.setattr(module, "_render_feedback", lambda *_args: "train feedback\n")
    context = OperatorContext(
        workspace=checkout,
        checkout=checkout,
        run_dir=checkout / "runs" / "gen-1",
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={"budget_tasks": 3, "jobs_dir": str(tmp_path / "jobs")},
        rng=random.Random(0),
    )

    result = module.HarborRollout().rollout(checkout, context)

    included = [captured[index + 1] for index, value in enumerate(captured) if value == "--include-task-name"]
    assert included == manifest["tasks"]["train"][:3]
    assert not set(included) & set(manifest["tasks"]["gate"] + manifest["tasks"]["sealed"])
    assert result.summary["split"] == "train"


def test_harbor_evaluator_shell_routes_gate_and_sealed_tasks(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "tasks")
    workspace = tmp_path / "workspace"
    initialized = run_evolve(
        "init",
        str(workspace),
        "--dataset",
        str(dataset),
        env={"EVOLVE_HOME": str(tmp_path / "evolve-home")},
    )
    assert initialized.returncode == 0, initialized.stderr
    manifest = json.loads((workspace / "evaluator" / "splits.json").read_text())
    eval_env = workspace / "evaluator" / "eval.env"
    eval_env.write_text(
        "\n".join(
            f'EVOLVE_JOBS_DIR="{tmp_path / "jobs"}"' if line.startswith("EVOLVE_JOBS_DIR=") else line
            for line in eval_env.read_text().splitlines()
        )
        + "\n"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_harbor = bin_dir / "harbor"
    fake_harbor.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "jobs = Path(args[args.index('--jobs-dir') + 1])\n"
        "attempts = int(args[args.index('--n-attempts') + 1])\n"
        "names = [args[i + 1] for i, value in enumerate(args) if value == '--include-task-name']\n"
        "for name in names:\n"
        "    for attempt in range(attempts):\n"
        "        verifier = jobs / f'{name}-{attempt}' / 'verifier'\n"
        "        verifier.mkdir(parents=True, exist_ok=True)\n"
        "        (verifier / 'reward.txt').write_text('1.0\\n')\n"
    )
    fake_harbor.chmod(0o755)

    for split_name in ("gate", "sealed"):
        run_dir = workspace / "runs" / f"manual-{split_name}"
        env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "EVOLVE_RUN_DIR": str(run_dir),
            "EVOLVE_GENID": "0",
            "EVOLVE_EVAL_SPLIT": split_name,
        }
        result = subprocess.run(
            [str(workspace / "evaluator" / "eval.sh")],
            cwd=workspace,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        selection = json.loads((run_dir / "task-split.json").read_text())
        expected = manifest["tasks"][split_name]
        if split_name == "gate":
            expected = expected[: manifest["gate_tasks_per_round"]]
        assert selection == {"split": split_name, "tasks": expected}
        assert (run_dir / "status").read_text() == "complete\n"
        metrics = json.loads((run_dir / "metrics.json").read_text())["dimensions"]
        assert metrics["expected_trials"] == len(expected)


def test_final_sealed_anchor_is_auxiliary_and_absent_from_mutator_lineage(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    rows = rows_by_genid(workspace)
    anchor_owner = next(
        row for row in rows.values() if any(entry.get("kind") == "anchor" for entry in row.get("evals", []))
    )
    anchor = next(entry for entry in anchor_owner["evals"] if entry.get("kind") == "anchor")
    assert anchor["task_set_hash"] != anchor_owner["task_set_hash"]
    assert anchor_owner["valid_parent"] is True

    feedback_dir = workspace / "runs" / "gen-2"
    write_feedback_bundle(workspace=workspace, run_dir=feedback_dir)
    lineage = json.loads((feedback_dir / "feedback" / "lineage.json").read_text())
    assert all("evals" not in row and "anchor" not in json.dumps(row) for row in lineage)
