import os
import stat
import subprocess
from pathlib import Path

from evolve.config import resource_root
from evolve.workspace import _eval_env, _eval_sh


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_harbor_registry_dataset_uses_dataset_flag_and_task_file(tmp_path: Path) -> None:
    evaluator = tmp_path / "evaluator"
    (evaluator / "tasks").mkdir(parents=True)
    _write_executable(evaluator / "eval.sh", _eval_sh("harbor", "swebenchpro@1.0"))
    (evaluator / "eval.env").write_text(
        _eval_env(
            "experiment",
            "swebenchpro@1.0",
            n_concurrent=1,
            tasks_per_round=1,
            trials=1,
            partial_floor=0.8,
            agent="mini-swe-agent",
            dataset_mode="registry",
            task_file="evaluator/tasks/train.txt",
        )
    )
    (evaluator / "tasks" / "train.txt").write_text("task-a\n# comment\n\ntask-b\n")
    (evaluator / "parse_score.py").write_text((resource_root("templates") / "evaluator/parse_score.py").read_text())

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
        "mkdir -p \"$jobs_dir/trial\"\n"
        "printf '%s\\n' '{\"verifier_result\":{\"rewards\":{\"reward\":1}}}' > \"$jobs_dir/trial/result.json\"\n",
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
    }
    result = subprocess.run([str(evaluator / "eval.sh")], cwd=tmp_path, env=env, text=True, capture_output=True)

    assert result.returncode == 0, result.stderr
    args = args_capture.read_text().splitlines()
    assert args[:3] == ["run", "--dataset", "swebenchpro@1.0"]
    assert "-p" not in args
    assert args.count("--include-task-name") == 2
    assert args[args.index("--include-task-name") + 1] == "task-a"
    assert args[args.index("--include-task-name", args.index("--include-task-name") + 1) + 1] == "task-b"
    assert args[args.index("--agent") + 1] == "mini-swe-agent"
    assert args[args.index("--model") + 1] == "openai/smoke-model"
    assert args[args.index("--agent-setup-timeout-multiplier") + 1] == "3"
    assert docker_host_capture.read_text() == "unset\n"
    assert (tmp_path / "run" / "status").read_text() == "complete\n"
