from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_benchmark_experiment.sh"
RUN = ROOT / "scripts" / "run_benchmark_experiment.sh"
SMOKE = ROOT / "scripts" / "configure_benchmark_smoke.sh"


def _run_setup(
    *args: str, env_overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "EVOLVE_EXPERIMENT_ROOT": "/tmp/evolve-experiments",
        "EVOLVE_FRAMEWORK": "/tmp/evolve-framework",
        "TAU3_DATASET": "/tmp/tau3-dataset",
        "TAU3_MANIFEST": "/tmp/tau3-splits.json",
        "TB2_DATASET": "/tmp/tb2-dataset",
        "TB2_MANIFEST": "/tmp/tb2-splits.json",
        **(env_overrides or {}),
    }
    return subprocess.run(
        ["bash", str(SETUP), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _values(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    assert result.returncode == 0, result.stderr
    return dict(line.split("=", 1) for line in result.stdout.splitlines())


def test_tau3_dry_run_resolves_frozen_counts_and_simulator() -> None:
    values = _values(_run_setup("ahe", "tau3", "ahe-tau3", "25", "--dry-run"))

    assert values["method"] == "ahe"
    assert values["benchmark"] == "tau3"
    assert values["tasks_per_round"] == "100"
    assert values["train_count"] == "100"
    assert values["gate_count"] == "100"
    assert values["sealed_count"] == "175"
    assert values["seed"] == "42"
    assert values["simulator_model"] == "openai/gpt-5.4-2026-03-05"
    assert values["simulator_effort"] == "low"


def test_terminal_bench_dry_run_resolves_frozen_counts() -> None:
    values = _values(
        _run_setup(
            "hyperagents",
            "terminal-bench-2",
            "hyperagents-terminal-bench-2",
            "25",
            "--dry-run",
        )
    )

    assert values["method"] == "hyperagents"
    assert values["benchmark"] == "terminal-bench-2"
    assert values["tasks_per_round"] == "50"
    assert values["train_count"] == "50"
    assert values["gate_count"] == "19"
    assert values["sealed_count"] == "20"
    assert values["seed"] == "0"
    assert values["simulator_model"] == "n/a"
    assert values["simulator_effort"] == "n/a"


def test_setup_rejects_unknown_method_and_benchmark() -> None:
    invalid_method = _run_setup(
        "gepa", "tau3", "gepa-tau3", "25", "--dry-run"
    )
    invalid_benchmark = _run_setup(
        "ahe", "hle", "ahe-hle", "25", "--dry-run"
    )

    assert invalid_method.returncode == 2
    assert invalid_benchmark.returncode == 2


def test_setup_rejects_unsafe_name_and_nonpositive_concurrency() -> None:
    unsafe_name = _run_setup(
        "ahe", "tau3", "../ahe-tau3", "25", "--dry-run"
    )
    zero_concurrency = _run_setup(
        "ahe", "tau3", "ahe-tau3", "0", "--dry-run"
    )

    assert unsafe_name.returncode == 2
    assert zero_concurrency.returncode == 2


def _write_fake_evolve(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
from pathlib import Path

args = sys.argv[1:]
if args[0] == "verify":
    raise SystemExit(0)
if args[0] != "init":
    raise SystemExit(f"unsupported fake command: {args}")
workspace = Path(args[1])
recipe = args[args.index("--recipe") + 1]
workspace.mkdir(parents=True)
(workspace / "evaluator").mkdir()
shutil.copy(
    Path(os.environ["FAKE_RECIPE_ROOT"]) / recipe / "evolve.yaml",
    workspace / "evolve.yaml",
)
(workspace / "evaluator" / "eval.env").write_text("EVOLVE_HARBOR_N_CONCURRENT=10\\n")
(workspace / "evaluator" / "eval.sh").write_text(
    'if [ -n "${EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER:-}" ]; then\\n'
    '  set -- "$@" --agent-setup-timeout-multiplier '
    '"$EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER"\\n'
    "fi\\n"
)
(workspace / "evaluator" / "agent.env").write_text("")
subprocess.run(["git", "init", "-q", str(workspace)], check=True)
subprocess.run(["git", "-C", str(workspace), "add", "."], check=True)
subprocess.run(
    [
        "git",
        "-C",
        str(workspace),
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "gen 0",
    ],
    check=True,
)
subprocess.run(["git", "-C", str(workspace), "tag", "gen/0"], check=True)
"""
    )
    path.chmod(0o755)


def _tau3_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, list[str]]]:
    dataset = tmp_path / "tau3"
    dataset.mkdir()
    categories = (
        "airline",
        "banking_knowledge-task",
        "retail",
        "telecom-case",
    )

    def task_names(count: int, offset: int) -> list[str]:
        return [
            f"tau3-{categories[index % len(categories)]}-{index + offset:03d}"
            for index in range(count)
        ]

    tasks = {
        "train": task_names(100, 0),
        "gate": task_names(100, 100),
        "sealed": task_names(175, 200),
    }
    for name in tasks["train"] + tasks["gate"] + tasks["sealed"]:
        task = dataset / name
        task.mkdir()
        (task / "task.toml").write_text("[task]\\n")
    manifest = tmp_path / "tau3-splits.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "dataset": "tau3-bench",
                "resolved": True,
                "seed": 42,
                "sampling": "static",
                "gate_tasks_per_round": 100,
                "ratios": {
                    "train": 100 / 375,
                    "gate": 100 / 375,
                    "sealed": 175 / 375,
                },
                "tasks": tasks,
            }
        )
    )
    return dataset, manifest, tasks


def _tb2_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, list[str]]]:
    dataset = tmp_path / "tb2"
    dataset.mkdir()
    tasks = {
        "train": [f"tb2-train-{index}" for index in range(50)],
        "gate": [f"tb2-gate-{index}" for index in range(19)],
        "sealed": [f"tb2-sealed-{index}" for index in range(20)],
    }
    for name in tasks["train"] + tasks["gate"] + tasks["sealed"]:
        task = dataset / name
        task.mkdir()
        (task / "task.toml").write_text("[task]\n")
    manifest = tmp_path / "tb2-splits.json"
    manifest.write_text(json.dumps(tasks))
    return dataset, manifest, tasks


def test_setup_renders_train_only_tau3_workspace_with_simulator(
    tmp_path: Path,
) -> None:
    fake_evolve = tmp_path / "evolve"
    _write_fake_evolve(fake_evolve)
    dataset, manifest, tasks = _tau3_fixture(tmp_path)
    experiment_root = tmp_path / "experiments"

    result = _run_setup(
        "ahe",
        "tau3",
        "ahe-tau3",
        "25",
        env_overrides={
            "EVOLVE_EXPERIMENT_ROOT": str(experiment_root),
            "EVOLVE_CLI": str(fake_evolve),
            "EVOLVE_PYTHON": sys.executable,
            "FAKE_RECIPE_ROOT": str(ROOT / "recipes"),
            "TAU3_DATASET": str(dataset),
            "TAU3_MANIFEST": str(manifest),
        },
    )

    assert result.returncode == 0, result.stderr
    workspace = experiment_root / "workspaces" / "ahe-tau3"
    config = yaml.safe_load((workspace / "evolve.yaml").read_text())
    evaluator = config["evaluator"]
    assert "budget_usd" not in config["experiment"]
    assert config["experiment"]["max_generations"] == 10
    assert evaluator["model"] == "openai/gpt-5.4-2026-03-05"
    assert evaluator["evaluation_split"] == "train"
    assert evaluator["sampling"] == "static"
    assert evaluator["tasks_per_round"] == 100
    assert evaluator["n_concurrent"] == 25
    assert evaluator["agent_setup_timeout_multiplier"] == 1
    assert evaluator["agent_timeout_multiplier"] == 2
    assert evaluator["max_retries"] == 1
    assert evaluator["anchor"] == {"final": True, "every_rounds": 0}
    assert evaluator["agent_env"]["MINISWE_REASONING_EFFORT"] == "high"
    assert "OPENAI_API_BASE" not in evaluator["agent_env"]
    assert "OPENAI_BASE_URL" not in evaluator["agent_env"]
    assert "NO_PROXY" not in evaluator["agent_env"]
    assert "no_proxy" not in evaluator["agent_env"]
    meta = config["operators"]["meta_agent"]
    assert meta["agent"] == "codex"
    assert meta["model"] == "gpt-5.4"
    assert meta["agent_kwargs"]["reasoning_effort"] == "xhigh"
    assert meta["timeout_s"] == 7200

    rendered_manifest = json.loads(
        (workspace / "evaluator" / "splits.json").read_text()
    )
    assert rendered_manifest["tasks"] == tasks
    assert (workspace / "evaluator" / "tasks" / "train.txt").read_text().splitlines() == tasks[
        "train"
    ]
    assert (workspace / "evaluator" / "tasks" / "sealed.txt").read_text().splitlines() == tasks[
        "sealed"
    ]
    simulator = dict(
        line.split("=", 1)
        for line in (workspace / "evaluator" / "simulator.env").read_text().splitlines()
    )
    assert simulator == {
        "TAU2_NL_ASSERTIONS_MODEL": "openai/gpt-5.4-2026-03-05",
        "TAU2_USER_MODEL": "openai/gpt-5.4-2026-03-05",
        "TAU2_USER_REASONING_EFFORT": "low",
    }


def test_setup_renders_terminal_bench_without_tau3_simulator(
    tmp_path: Path,
) -> None:
    fake_evolve = tmp_path / "evolve"
    _write_fake_evolve(fake_evolve)
    dataset, manifest, tasks = _tb2_fixture(tmp_path)
    experiment_root = tmp_path / "experiments"

    result = _run_setup(
        "hyperagents",
        "terminal-bench-2",
        "hyperagents-terminal-bench-2",
        "25",
        env_overrides={
            "EVOLVE_EXPERIMENT_ROOT": str(experiment_root),
            "EVOLVE_CLI": str(fake_evolve),
            "EVOLVE_PYTHON": sys.executable,
            "FAKE_RECIPE_ROOT": str(ROOT / "recipes"),
            "TB2_DATASET": str(dataset),
            "TB2_MANIFEST": str(manifest),
        },
    )

    assert result.returncode == 0, result.stderr
    workspace = experiment_root / "workspaces" / "hyperagents-terminal-bench-2"
    config = yaml.safe_load((workspace / "evolve.yaml").read_text())
    evaluator = config["evaluator"]
    assert "budget_usd" not in config["experiment"]
    assert evaluator["tasks_per_round"] == 50
    assert evaluator["evaluation_split"] == "train"
    assert config["operators"]["meta_agent"]["variant"] == "hyperagents"
    assert config["operators"]["trace_analyzer"]["variant"] == "trace_browser"
    assert config["operators"]["gate"]["variant"] == "parent_eligible"
    assert not (workspace / "evaluator" / "simulator.env").exists()
    rendered_manifest = json.loads(
        (workspace / "evaluator" / "splits.json").read_text()
    )
    assert rendered_manifest["tasks"] == tasks


def _run_workspace(
    *args: str, env_overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "EVOLVE_EXPERIMENT_ROOT": "/tmp/evolve-experiments",
        "EVOLVE_FRAMEWORK": "/tmp/evolve-framework",
        **(env_overrides or {}),
    }
    return subprocess.run(
        ["bash", str(RUN), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_dry_run_resolves_workspace_and_generations() -> None:
    values = _values(_run_workspace("ahe-tau3", "10", "--dry-run"))

    assert values["workspace"] == "/tmp/evolve-experiments/workspaces/ahe-tau3"
    assert values["runner"] == "/tmp/evolve-framework/.venv/bin/evolve"
    assert values["framework_python"] == "/tmp/evolve-framework/.venv/bin/python"
    assert values["max_generations"] == "10"


def test_run_rejects_unsafe_name_and_nonpositive_generations() -> None:
    unsafe_name = _run_workspace("../ahe-tau3", "10", "--dry-run")
    zero_generations = _run_workspace("ahe-tau3", "0", "--dry-run")

    assert unsafe_name.returncode == 2
    assert zero_generations.returncode == 2


def test_run_verifies_then_launches_with_tau3_simulator_environment(
    tmp_path: Path,
) -> None:
    root = tmp_path / "experiments"
    workspace = root / "workspaces" / "ahe-tau3-smoke"
    simulator = workspace / "evaluator" / "simulator.env"
    simulator.parent.mkdir(parents=True)
    simulator.write_text(
        "TAU2_NL_ASSERTIONS_MODEL=openai/gpt-5.4-2026-03-05\n"
        "TAU2_USER_MODEL=openai/gpt-5.4-2026-03-05\n"
        "TAU2_USER_REASONING_EFFORT=low\n"
    )
    (workspace / "evaluator" / "eval.env").write_text(
        "EVOLVE_HARBOR_N_CONCURRENT=5\n"
    )
    (root / "evolve.env").write_text(
        "TEST_EVOLVE_ENV=loaded\nEVOLVE_HARBOR_N_CONCURRENT_OVERRIDE=25\n"
    )
    (root / "runtime.env").write_text("TEST_RUNTIME_ENV=loaded\n")
    runner = tmp_path / "fake-evolve"
    log = tmp_path / "calls.jsonl"
    runner.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["FAKE_EVOLVE_LOG"], "a") as handle:
    handle.write(json.dumps({
        "args": sys.argv[1:],
        "simulator_model": os.environ.get("TAU2_USER_MODEL"),
        "simulator_effort": os.environ.get("TAU2_USER_REASONING_EFFORT"),
        "evolve_env": os.environ.get("TEST_EVOLVE_ENV"),
        "runtime_env": os.environ.get("TEST_RUNTIME_ENV"),
        "concurrency_override": os.environ.get("EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE"),
    }) + "\\n")
"""
    )
    runner.chmod(0o755)

    result = _run_workspace(
        "ahe-tau3-smoke",
        "3",
        env_overrides={
            "EVOLVE_EXPERIMENT_ROOT": str(root),
            "EVOLVE_CLI": str(runner),
            "EVOLVE_PYTHON": sys.executable,
            "FAKE_EVOLVE_LOG": str(log),
        },
    )

    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls[0]["args"] == ["verify", str(workspace)]
    assert calls[1]["args"] == [
        "run",
        str(workspace),
        "--max-generations",
        "3",
    ]
    assert calls[1]["simulator_model"] == "openai/gpt-5.4-2026-03-05"
    assert calls[1]["simulator_effort"] == "low"
    assert calls[1]["evolve_env"] == "loaded"
    assert calls[1]["runtime_env"] == "loaded"
    assert calls[1]["concurrency_override"] == "5"


def test_smoke_config_selects_exact_train_subset_and_disables_anchor(
    tmp_path: Path,
) -> None:
    fake_evolve = tmp_path / "evolve"
    _write_fake_evolve(fake_evolve)
    dataset, manifest, original_tasks = _tau3_fixture(tmp_path)
    root = tmp_path / "experiments"
    setup = _run_setup(
        "ahe",
        "tau3",
        "ahe-tau3-smoke-5x3",
        "25",
        env_overrides={
            "EVOLVE_EXPERIMENT_ROOT": str(root),
            "EVOLVE_CLI": str(fake_evolve),
            "EVOLVE_PYTHON": sys.executable,
            "FAKE_RECIPE_ROOT": str(ROOT / "recipes"),
            "TAU3_DATASET": str(dataset),
            "TAU3_MANIFEST": str(manifest),
        },
    )
    assert setup.returncode == 0, setup.stderr
    workspace = root / "workspaces" / "ahe-tau3-smoke-5x3"

    configured = subprocess.run(
        ["bash", str(SMOKE), str(workspace), "5", "3", "5"],
        cwd=ROOT,
        env={
            **os.environ,
            "EVOLVE_CLI": str(fake_evolve),
            "EVOLVE_PYTHON": sys.executable,
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert configured.returncode == 0, configured.stderr
    config = yaml.safe_load((workspace / "evolve.yaml").read_text())
    rendered = json.loads((workspace / "evaluator" / "splits.json").read_text())
    selected = [
        "tau3-airline-000",
        "tau3-banking_knowledge-task-001",
        "tau3-retail-002",
        "tau3-telecom-case-003",
        "tau3-airline-004",
    ]
    assert config["experiment"]["max_generations"] == 3
    assert config["evaluator"]["tasks_per_round"] == 5
    assert config["evaluator"]["task_names"] == selected
    assert config["evaluator"]["agent_env"]["MINISWE_STEP_LIMIT"] == "12"
    assert config["evaluator"]["anchor"]["final"] is False
    assert config["operators"]["trace_analyzer"]["max_tasks"] == 1
    assert config["operators"]["trace_analyzer"]["max_concurrent"] == 1
    agent_env = dict(
        line.split("=", 1)
        for line in (workspace / "evaluator" / "agent.env").read_text().splitlines()
    )
    assert agent_env["MINISWE_STEP_LIMIT"] == "12"
    eval_env = dict(
        line.split("=", 1)
        for line in (workspace / "evaluator" / "eval.env").read_text().splitlines()
    )
    assert eval_env["EVOLVE_HARBOR_ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER"] == "10"
    assert "--environment-build-timeout-multiplier" in (
        workspace / "evaluator" / "eval.sh"
    ).read_text()
    assert rendered["tasks"]["train"] == selected
    assert set(rendered["tasks"]["train"]).isdisjoint(rendered["tasks"]["gate"])
    assert set(rendered["tasks"]["train"]).isdisjoint(rendered["tasks"]["sealed"])
    assert sorted(
        rendered["tasks"]["train"]
        + rendered["tasks"]["gate"]
        + rendered["tasks"]["sealed"]
    ) == sorted(
        original_tasks["train"]
        + original_tasks["gate"]
        + original_tasks["sealed"]
    )
    assert (
        workspace / "evaluator" / "smoke-task-names.txt"
    ).read_text().splitlines() == selected
