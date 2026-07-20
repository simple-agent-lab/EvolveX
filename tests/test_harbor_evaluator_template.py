import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from evolve.config import resource_root
from evolve.workspace import _eval_env, _eval_sh


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_evaluator_helpers(evaluator: Path) -> None:
    for name in ("harbor_artifacts.py", "parse_score.py", "cleanup_harbor.py"):
        (evaluator / name).write_text((resource_root("templates") / "evaluator" / name).read_text())


def _write_fake_uv(bin_dir: Path) -> None:
    _write_executable(
        bin_dir / "uv",
        "#!/bin/sh\n"
        '[ "$1" = run ] || exit 90\n'
        "shift\n"
        '[ "$1" = --project ] || exit 91\n'
        "shift 2\n"
        '[ "$1" = --frozen ] || exit 92\n'
        "shift\n"
        'exec "$@"\n',
    )


def test_harbor_evaluator_uses_locked_workspace_runtime() -> None:
    text = _eval_sh("harbor", "fixture")

    assert "PYTHONPATH" not in text
    assert 'run --project "$EVOLVE_WORKSPACE" --frozen harbor' in text
    assert '"$PWD/.evolve/launch_splits.py"' in text


def test_harbor_evaluator_passes_agent_timeout_multiplier() -> None:
    text = _eval_sh("harbor", "fixture")

    assert '--agent-timeout-multiplier "$EVOLVE_HARBOR_AGENT_TIMEOUT_MULTIPLIER"' in text


def test_harbor_evaluator_prefers_failed_task_repair_selection() -> None:
    text = _eval_sh("harbor", "fixture")

    repair_override = "EVOLVE_HARBOR_TASK_FILE=$EVOLVE_REPAIR_TASK_FILE"
    assert repair_override in text
    assert text.index(repair_override) > text.index('EVOLVE_HARBOR_TASK_FILE="$EVOLVE_RUN_DIR/task-names.txt"')
    assert text.index(repair_override) < text.index('--include-task-name "$task_name"')


def test_harbor_stage_limit_and_anchor_task_file_override(tmp_path: Path) -> None:
    evaluator = tmp_path / "evaluator"
    (evaluator / "tasks").mkdir(parents=True)
    _write_executable(evaluator / "eval.sh", _eval_sh("harbor", "swebenchpro@1.0"))
    (evaluator / "eval.env").write_text(
        _eval_env(
            "experiment",
            "swebenchpro@1.0",
            n_concurrent=16,
            tasks_per_round=4,
            trials=1,
            partial_floor=0.8,
            agent="mini-swe-agent",
            dataset_mode="registry",
            task_file="evaluator/tasks/train.txt",
        )
        + "EVOLVE_HARBOR_ANCHOR_TASK_FILE=evaluator/tasks/sealed.txt\n"
    )
    (evaluator / "tasks" / "train.txt").write_text("train-task\n")
    (evaluator / "tasks" / "sealed.txt").write_text("sealed-a\nsealed-b\n")
    _write_evaluator_helpers(evaluator)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_uv(fake_bin)
    _write_executable(
        fake_bin / "harbor",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$@" > "$HARBOR_ARGS_CAPTURE"\n'
        "jobs_dir=\n"
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--jobs-dir" ]; then\n'
        "    shift\n"
        "    jobs_dir=$1\n"
        "  fi\n"
        "  shift || true\n"
        "done\n"
        'mkdir -p "$jobs_dir/trial-a" "$jobs_dir/trial-b"\n'
        'printf \'%s\\n\' \'{"task_name":"sealed-a","trial_name":"trial-a","verifier_result":{"rewards":{"reward":1}}}\' > "$jobs_dir/trial-a/result.json"\n'
        'printf \'%s\\n\' \'{"task_name":"sealed-b","trial_name":"trial-b","verifier_result":{"rewards":{"reward":1}}}\' > "$jobs_dir/trial-b/result.json"\n',
    )

    args_capture = tmp_path / "harbor-args.txt"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "HARBOR_ARGS_CAPTURE": str(args_capture),
        "EVOLVE_RUN_DIR": str(tmp_path / "run"),
        "EVOLVE_EVAL_KIND": "anchor",
        "EVOLVE_TASK_LIMIT": "2",
        "EVOLVE_ATTEMPT_ID": "anchor-attempt",
        "EVOLVE_FRAMEWORK_PYTHON": sys.executable,
    }
    result = subprocess.run([str(evaluator / "eval.sh")], cwd=tmp_path, env=env, text=True, capture_output=True)

    assert result.returncode == 0, result.stderr
    args = args_capture.read_text().splitlines()
    assert args.count("--include-task-name") == 2
    assert "sealed-a" in args
    assert "sealed-b" in args
    assert "train-task" not in args
    assert args[args.index("--n-tasks") + 1] == "2"
    assert (tmp_path / "run" / "metrics.json").read_text().count('"expected_trials": 2') == 1


def test_harbor_smoke_is_install_only_and_exposes_raw_diagnostics(tmp_path: Path) -> None:
    evaluator = tmp_path / "evaluator"
    evaluator.mkdir()
    _write_executable(evaluator / "eval.sh", _eval_sh("harbor", "fixture"))
    (evaluator / "eval.env").write_text(
        _eval_env(
            "experiment",
            "fixture",
            n_concurrent=8,
            tasks_per_round=8,
            trials=2,
            partial_floor=0.8,
            agent="evolve_harbor_adapter:MiniSweSourceAgent",
        )
    )
    _write_evaluator_helpers(evaluator)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_uv(fake_bin)
    _write_executable(
        fake_bin / "harbor",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$@" > "$HARBOR_ARGS_CAPTURE"\n'
        "jobs_dir=\n"
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--jobs-dir" ]; then shift; jobs_dir=$1; fi\n'
        "  shift || true\n"
        "done\n"
        "printf '%s\\n' \"ModuleNotFoundError: No module named 'fastapi'\" >&2\n"
        "exit 7\n",
    )
    run_dir = tmp_path / "run"
    cache = tmp_path / "shared-cache"
    args_capture = tmp_path / "args"
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "HARBOR_ARGS_CAPTURE": str(args_capture),
        "EVOLVE_RUN_DIR": str(run_dir),
        "EVOLVE_CANDIDATE_SMOKE_MODE": "full",
        "EVOLVE_UV_CACHE_DIR": str(cache),
        "EVOLVE_ATTEMPT_ID": "smoke-attempt",
        "EVOLVE_FRAMEWORK_PYTHON": sys.executable,
    }

    result = subprocess.run([str(evaluator / "eval.sh")], cwd=tmp_path, env=env, text=True, capture_output=True)

    assert result.returncode == 7
    assert "ModuleNotFoundError: No module named 'fastapi'" in result.stderr
    args = args_capture.read_text().splitlines()
    assert "--install-only" in args
    assert "EVOLVE_CANDIDATE_SMOKE_MODE=full" in args
    assert f"EVOLVE_CANDIDATE_SOURCE={tmp_path / 'target'}" in args
    assert args[args.index("--n-tasks") + 1] == "1"
    assert args[args.index("--n-attempts") + 1] == "1"
    assert args[args.index("-n") + 1] == "1"
    mounts = json.loads(args[args.index("--mounts") + 1])
    assert mounts[0]["source"] == str(cache)
    assert not (run_dir / "harbor-result.json").exists()
    assert not (run_dir / "score").exists()
