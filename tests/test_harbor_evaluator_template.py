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


def test_harbor_registry_dataset_uses_dataset_flag_and_task_file(tmp_path: Path) -> None:
    evaluator = tmp_path / "evaluator"
    (evaluator / "tasks").mkdir(parents=True)
    _write_executable(evaluator / "eval.sh", _eval_sh("harbor", "swebenchpro@1.0"))
    (evaluator / "eval.env").write_text(
        _eval_env(
            "experiment",
            "swebenchpro@1.0",
            n_concurrent=5,
            tasks_per_round=2,
            trials=2,
            partial_floor=0.8,
            agent="mini-swe-agent",
            dataset_mode="registry",
            task_file="evaluator/tasks/train.txt",
        )
    )
    (evaluator / "tasks" / "train.txt").write_text("case-a\n# comment\n\ncase-b\n")
    _write_evaluator_helpers(evaluator)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "harbor",
        "#!/bin/sh\n"
        "printf '%s\\n' \"$@\" > \"$HARBOR_ARGS_CAPTURE\"\n"
        "printf '%s\\n' \"${DOCKER_HOST-unset}\" > \"$HARBOR_DOCKER_HOST_CAPTURE\"\n"
        "jobs_dir=\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = \"--jobs-dir\" ]; then\n"
        "    shift\n"
        "    jobs_dir=$1\n"
        "  fi\n"
        "  shift || true\n"
        "done\n"
        "for task in case-a case-b; do\n"
        "  for trial in one two; do\n"
        "    mkdir -p \"$jobs_dir/${task}__${trial}\"\n"
        "    printf '%s\\n' \"{\\\"task_name\\\":\\\"$task\\\",\\\"trial_name\\\":\\\"$trial\\\",\\\"verifier_result\\\":{\\\"rewards\\\":{\\\"reward\\\":1}}}\" > \"$jobs_dir/${task}__${trial}/result.json\"\n"
        "  done\n"
        "done\n",
    )

    args_capture = tmp_path / "harbor-args.txt"
    docker_host_capture = tmp_path / "docker-host.txt"
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "HARBOR_ARGS_CAPTURE": str(args_capture),
        "HARBOR_DOCKER_HOST_CAPTURE": str(docker_host_capture),
        "EVOLVE_RUN_DIR": str(tmp_path / "run"),
        "OPENAI_MODEL": "smoke-model",
        "EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER": "3",
        "EVOLVE_UV_CACHE_DIR": str(tmp_path / "shared-uv-cache"),
        "EVOLVE_ATTEMPT_ID": "exact-attempt",
        "EVOLVE_FRAMEWORK_PYTHON": sys.executable,
    }
    result = subprocess.run([str(evaluator / "eval.sh")], cwd=tmp_path, env=env, text=True, capture_output=True)

    assert result.returncode == 0, result.stderr
    args = args_capture.read_text().splitlines()
    assert args[:3] == ["run", "--dataset", "swebenchpro@1.0"]
    assert args[args.index("--job-name") + 1] == "exact-attempt"
    assert "-p" not in args
    assert args.count("--include-task-name") == 2
    assert args[args.index("--include-task-name") + 1] == "case-a"
    assert args[args.index("--include-task-name", args.index("--include-task-name") + 1) + 1] == "case-b"
    assert args[args.index("--agent") + 1] == "mini-swe-agent"
    assert args[args.index("--model") + 1] == "openai/smoke-model"
    assert args[args.index("--agent-setup-timeout-multiplier") + 1] == "3"
    assert args[args.index("--n-attempts") + 1] == "2"
    assert args[args.index("--jobs-dir") + 1] == str(tmp_path / "run" / "jobs")
    mounts = json.loads(args[args.index("--mounts") + 1])
    assert mounts == [
        {
            "source": str(tmp_path / "shared-uv-cache"),
            "target": "/installed-agent/uv-cache",
            "type": "bind",
        }
    ]
    assert (tmp_path / "shared-uv-cache").is_dir()
    assert docker_host_capture.read_text() == "unset\n"
    assert (tmp_path / "run" / "status").read_text() == "complete\n"


def test_harbor_jobs_are_owned_by_run_and_existing_jobs_fail_without_deletion(tmp_path: Path) -> None:
    evaluator = tmp_path / "evaluator"
    evaluator.mkdir()
    _write_executable(evaluator / "eval.sh", _eval_sh("harbor", "fixture"))
    eval_env = _eval_env(
        "experiment", "fixture", n_concurrent=1, tasks_per_round=1,
        trials=1, partial_floor=0.8, agent="mini-swe-agent",
    )
    (evaluator / "eval.env").write_text(eval_env)
    assert "EVOLVE_JOBS_DIR" not in eval_env
    _write_evaluator_helpers(evaluator)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    jobs_capture = tmp_path / "jobs-capture"
    _write_executable(
        fake_bin / "harbor",
        "#!/bin/sh\n"
        "jobs_dir=\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = \"--jobs-dir\" ]; then shift; jobs_dir=$1; fi\n"
        "  shift || true\n"
        "done\n"
        "printf '%s\\n' \"$jobs_dir\" >> \"$JOBS_CAPTURE\"\n"
        "mkdir -p \"$jobs_dir/trial\"\n"
        "printf '%s\\n' '{\"task_name\":\"case-a\",\"trial_name\":\"trial\",\"verifier_result\":{\"rewards\":{\"reward\":1}}}' > \"$jobs_dir/trial/result.json\"\n",
    )
    base_env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "JOBS_CAPTURE": str(jobs_capture),
        "EVOLVE_FRAMEWORK_PYTHON": sys.executable,
    }
    first_run = tmp_path / "run-a"
    first = subprocess.run(
        [str(evaluator / "eval.sh")], cwd=tmp_path,
        env={**base_env, "EVOLVE_RUN_DIR": str(first_run), "EVOLVE_ATTEMPT_ID": "attempt-a"},
        text=True, capture_output=True, check=False,
    )
    assert first.returncode == 0, first.stderr
    first_marker = first_run / "jobs" / "owned-marker"
    first_marker.write_text("first\n")

    second_run = tmp_path / "run-b"
    second = subprocess.run(
        [str(evaluator / "eval.sh")], cwd=tmp_path,
        env={**base_env, "EVOLVE_RUN_DIR": str(second_run), "EVOLVE_ATTEMPT_ID": "attempt-b"},
        text=True, capture_output=True, check=False,
    )
    assert second.returncode == 0, second.stderr
    assert first_marker.read_text() == "first\n"
    assert jobs_capture.read_text().splitlines() == [
        str(first_run / "jobs"),
        str(second_run / "jobs"),
    ]

    blocked_run = tmp_path / "run-blocked"
    blocked_jobs = blocked_run / "jobs"
    blocked_jobs.mkdir(parents=True)
    blocked_marker = blocked_jobs / "do-not-delete"
    blocked_marker.write_text("owned elsewhere\n")
    blocked = subprocess.run(
        [str(evaluator / "eval.sh")], cwd=tmp_path,
        env={**base_env, "EVOLVE_RUN_DIR": str(blocked_run), "EVOLVE_ATTEMPT_ID": "attempt-blocked"},
        text=True, capture_output=True, check=False,
    )
    assert blocked.returncode == 3
    assert blocked_marker.read_text() == "owned elsewhere\n"
    assert jobs_capture.read_text().splitlines() == [str(first_run / "jobs"), str(second_run / "jobs")]


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
    _write_executable(
        fake_bin / "harbor",
        "#!/bin/sh\n"
        "printf '%s\\n' \"$@\" > \"$HARBOR_ARGS_CAPTURE\"\n"
        "jobs_dir=\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = \"--jobs-dir\" ]; then\n"
        "    shift\n"
        "    jobs_dir=$1\n"
        "  fi\n"
        "  shift || true\n"
        "done\n"
        "mkdir -p \"$jobs_dir/trial-a\" \"$jobs_dir/trial-b\"\n"
        "printf '%s\\n' '{\"task_name\":\"sealed-a\",\"trial_name\":\"trial-a\",\"verifier_result\":{\"rewards\":{\"reward\":1}}}' > \"$jobs_dir/trial-a/result.json\"\n"
        "printf '%s\\n' '{\"task_name\":\"sealed-b\",\"trial_name\":\"trial-b\",\"verifier_result\":{\"rewards\":{\"reward\":1}}}' > \"$jobs_dir/trial-b/result.json\"\n",
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


def test_nonzero_harbor_exit_overrides_reward_and_preserves_cost(tmp_path: Path) -> None:
    evaluator = tmp_path / "evaluator"
    evaluator.mkdir()
    _write_executable(evaluator / "eval.sh", _eval_sh("harbor", "fixture"))
    (evaluator / "eval.env").write_text(
        _eval_env(
            "experiment",
            "fixture",
            n_concurrent=1,
            tasks_per_round=1,
            trials=1,
            partial_floor=0.8,
            agent="mini-swe-agent",
        )
    )
    _write_evaluator_helpers(evaluator)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "harbor",
        "#!/bin/sh\n"
        "jobs_dir=\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = \"--jobs-dir\" ]; then shift; jobs_dir=$1; fi\n"
        "  shift || true\n"
        "done\n"
        "mkdir -p \"$jobs_dir/case-a__one\"\n"
        "printf '%s\\n' '{\"task_name\":\"case-a\",\"trial_name\":\"one\",\"verifier_result\":{\"rewards\":{\"reward\":0}},\"agent_result\":{\"cost_usd\":0.4}}' > \"$jobs_dir/case-a__one/result.json\"\n"
        "printf '%s\\n' '{\"trial_name\":\"Task/ABC.1\"}' > \"$jobs_dir/case-a__one/config.json\"\n"
        "exit 9\n",
    )
    docker_calls = tmp_path / "docker-calls"
    _write_executable(
        fake_bin / "docker",
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$DOCKER_CALLS\"\n"
        "if [ \"$1\" = ps ]; then printf 'owned-container\\n'; fi\n",
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "EVOLVE_RUN_DIR": str(tmp_path / "run"),
        "EVOLVE_ATTEMPT_ID": "failed-attempt",
        "EVOLVE_FRAMEWORK_PYTHON": sys.executable,
        "DOCKER_CALLS": str(docker_calls),
    }

    result = subprocess.run([str(evaluator / "eval.sh")], cwd=tmp_path, env=env, text=True, capture_output=True)

    assert result.returncode == 3
    assert (tmp_path / "run" / "status").read_text() == "infra_failed\n"
    assert not (tmp_path / "run" / "score").exists()
    assert (tmp_path / "run" / "cost.json").read_text() == '{"usd": 0.4}\n'
    assert docker_calls.read_text().splitlines() == [
        "ps -aq --filter label=com.docker.compose.project=task-abc-1__env",
        "rm -f owned-container",
    ]


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
            agent="target.harbor_agent:MiniSweSourceAgent",
        )
    )
    _write_evaluator_helpers(evaluator)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "harbor",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$@" > "$HARBOR_ARGS_CAPTURE"\n'
        "jobs_dir=\n"
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--jobs-dir" ]; then shift; jobs_dir=$1; fi\n'
        "  shift || true\n"
        "done\n"
        'printf \'%s\\n\' "ModuleNotFoundError: No module named \'fastapi\'" >&2\n'
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
    assert args[args.index("--ae") + 1] == "EVOLVE_CANDIDATE_SMOKE_MODE=full"
    assert args[args.index("--n-tasks") + 1] == "1"
    assert args[args.index("--n-attempts") + 1] == "1"
    assert args[args.index("-n") + 1] == "1"
    mounts = json.loads(args[args.index("--mounts") + 1])
    assert mounts[0]["source"] == str(cache)
    assert not (run_dir / "harbor-result.json").exists()
    assert not (run_dir / "score").exists()
