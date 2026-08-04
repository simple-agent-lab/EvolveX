import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from evolve.config import scaffold_root
from evolve.workspace import _eval_env, _eval_sh


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_evaluator_helpers(evaluator: Path) -> None:
    for name in ("harbor_artifacts.py", "parse_score.py", "cleanup_harbor.py"):
        (evaluator / name).write_text((scaffold_root() / "evaluators" / "harbor" / name).read_text())


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


def test_harbor_evaluator_passes_verifier_timeout_multiplier() -> None:
    text = _eval_sh("harbor", "fixture")

    assert '--verifier-timeout-multiplier "$EVOLVE_HARBOR_VERIFIER_TIMEOUT_MULTIPLIER"' in text


def test_harbor_evaluator_ignores_ambient_frozen_control_overrides(tmp_path: Path) -> None:
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
            partial_floor=0.9,
            agent="custom:Agent",
            setup_timeout_multiplier=1,
            agent_timeout_multiplier=1,
            verifier_timeout_multiplier=1,
            max_retries=0,
        )
    )
    (evaluator / "agent.env").write_text("")
    (evaluator / "verifier.env").write_text("")
    (evaluator / "environment.kwargs").write_text("")
    (evaluator / "splits.json").write_text('{"resolved":false}\n')
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
        'mkdir -p "$jobs_dir/trial"\n'
        'printf \'%s\\n\' \'{"task_name":"task","trial_name":"trial","verifier_result":{"rewards":{"reward":1}}}\' > "$jobs_dir/trial/result.json"\n',
    )
    _write_executable(fake_bin / "docker", "#!/bin/sh\nexit 0\n")

    args_capture = tmp_path / "args"
    run_dir = tmp_path / "run"
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "HARBOR_ARGS_CAPTURE": str(args_capture),
        "EVOLVE_RUN_DIR": str(run_dir),
        "EVOLVE_ATTEMPT_ID": "ambient-override-test",
        "EVOLVE_FRAMEWORK_PYTHON": sys.executable,
        "EVOLVE_CANDIDATE_RUNTIME_ENV_JSON": "{}",
        "EVOLVE_CANDIDATE_RUNTIME_MOUNTS_JSON": "[]",
        "EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE": "2",
        "EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER": "9",
        "EVOLVE_HARBOR_AGENT_TIMEOUT_MULTIPLIER": "9",
        "EVOLVE_HARBOR_VERIFIER_TIMEOUT_MULTIPLIER": "9",
        "EVOLVE_HARBOR_MAX_RETRIES": "9",
    }

    result = subprocess.run(
        [str(evaluator / "eval.sh")],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    args = args_capture.read_text().splitlines()
    assert args[args.index("-n") + 1] == "2"
    assert "--agent-setup-timeout-multiplier" not in args
    assert "--agent-timeout-multiplier" not in args
    assert "--verifier-timeout-multiplier" not in args
    assert "--max-retries" not in args


def test_harbor_shell_consumes_prevalidated_environment_inputs() -> None:
    text = _eval_sh("harbor", "fixture")

    assert 'done < "$EVOLVE_RUN_DIR/runtime-agent.env"' in text
    assert 'done < "$EVOLVE_RUN_DIR/runtime-verifier.env"' in text
    assert "for credential_name in" not in text
    assert "dependency_hosts =" not in text
    assert "model_base=" not in text


def test_harbor_evaluator_translates_environment_inputs_and_skips_docker_cleanup(
    tmp_path: Path,
) -> None:
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
            agent="custom:Agent",
            environment="evolve.harbor_local:LocalEnvironment",
        )
    )
    (evaluator / "environment.kwargs").write_text('workdir="/workspace"\n')
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
        'mkdir -p "$jobs_dir/trial"\n'
        'printf \'%s\\n\' \'{"task_name":"task","trial_name":"trial","verifier_result":{"rewards":{"reward":1}}}\' > "$jobs_dir/trial/result.json"\n',
    )
    _write_executable(fake_bin / "docker", '#!/bin/sh\nprintf called > "$DOCKER_MARKER"\n')
    args_capture = tmp_path / "args"
    docker_marker = tmp_path / "docker-called"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    run_dir.chmod(0o700)
    (run_dir / "runtime-agent.env").write_text(
        "HTTPS_PROXY=${EVOLVE_RUNTIME_AGENT_HTTPS_PROXY}\n"
        "NO_PROXY=${EVOLVE_RUNTIME_AGENT_NO_PROXY}\n"
    )
    (run_dir / "runtime-verifier.env").write_text(
        "HTTPS_PROXY=${EVOLVE_RUNTIME_VERIFIER_HTTPS_PROXY}\n"
        "JUDGE_MODEL=${EVOLVE_RUNTIME_VERIFIER_JUDGE_MODEL}\n"
        "NO_PROXY=${EVOLVE_RUNTIME_VERIFIER_NO_PROXY}\n"
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "HARBOR_ARGS_CAPTURE": str(args_capture),
        "DOCKER_MARKER": str(docker_marker),
        "EVOLVE_RUN_DIR": str(run_dir),
        "EVOLVE_ATTEMPT_ID": "local-attempt",
        "EVOLVE_FRAMEWORK_PYTHON": sys.executable,
        "EVOLVE_RUNTIME_AGENT_HTTPS_PROXY": "http://dependency-proxy.example:8118",
        "EVOLVE_RUNTIME_AGENT_NO_PROXY": ".internal.example,.upper.example,model.example",
        "EVOLVE_RUNTIME_VERIFIER_HTTPS_PROXY": "http://dependency-proxy.example:8118",
        "EVOLVE_RUNTIME_VERIFIER_JUDGE_MODEL": "gpt-5.4-mini-2026-03-17",
        "EVOLVE_RUNTIME_VERIFIER_NO_PROXY": ".internal.example,.upper.example,model.example",
    }

    result = subprocess.run([str(evaluator / "eval.sh")], cwd=tmp_path, env=env, text=True, capture_output=True)

    assert result.returncode == 0, result.stderr
    args = args_capture.read_text().splitlines()
    assert args[args.index("--env") + 1] == "evolve.harbor_local:LocalEnvironment"
    assert args[args.index("--environment-kwarg") + 1] == 'workdir="/workspace"'
    agent_environment = [args[index + 1] for index, value in enumerate(args) if value == "--ae"]
    verifier_environment = [args[index + 1] for index, value in enumerate(args) if value == "--ve"]
    assert "HTTPS_PROXY=${EVOLVE_RUNTIME_AGENT_HTTPS_PROXY}" in agent_environment
    assert "NO_PROXY=${EVOLVE_RUNTIME_AGENT_NO_PROXY}" in agent_environment
    assert "HTTPS_PROXY=${EVOLVE_RUNTIME_VERIFIER_HTTPS_PROXY}" in verifier_environment
    assert "JUDGE_MODEL=${EVOLVE_RUNTIME_VERIFIER_JUDGE_MODEL}" in verifier_environment
    assert "JUDGE_MODEL=${EVOLVE_RUNTIME_VERIFIER_JUDGE_MODEL}" not in agent_environment
    assert not docker_marker.exists()
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((run_dir / "candidate-runtime.env").stat().st_mode) == 0o600
    assert stat.S_IMODE((run_dir / "jobs").stat().st_mode) == 0o700
    assert stat.S_IMODE((run_dir / "jobs" / "trial" / "result.json").stat().st_mode) == 0o600


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
            agent="evolve.integrations.harbor.miniswe_candidate:MiniSweSourceAgent",
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
    python_dir = tmp_path / "shared-python"
    runtime_mounts = [
        {
            "type": "bind",
            "source": str(cache),
            "target": "/opt/evolve/uv/cache",
            "read_only": False,
        },
        {
            "type": "bind",
            "source": str(python_dir),
            "target": "/opt/evolve/uv/python",
            "read_only": False,
        },
    ]
    runtime_env = {
        "UV_CACHE_DIR": "/opt/evolve/uv/cache",
        "UV_LINK_MODE": "copy",
        "UV_OFFLINE": "1",
        "UV_PYTHON_INSTALL_DIR": "/opt/evolve/uv/python",
    }
    args_capture = tmp_path / "args"
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "HARBOR_ARGS_CAPTURE": str(args_capture),
        "EVOLVE_RUN_DIR": str(run_dir),
        "EVOLVE_CANDIDATE_SMOKE_MODE": "full",
        "EVOLVE_CANDIDATE_RUNTIME_MOUNTS_JSON": json.dumps(runtime_mounts),
        "EVOLVE_CANDIDATE_RUNTIME_ENV_JSON": json.dumps(runtime_env),
        "EVOLVE_TASK_LIMIT": "8",
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
    assert args[args.index("--n-tasks") + 1] == "8"
    assert args[args.index("--n-attempts") + 1] == "1"
    assert args[args.index("-n") + 1] == "8"
    mounts = json.loads(args[args.index("--mounts") + 1])
    assert mounts == runtime_mounts
    agent_environment = [args[index + 1] for index, value in enumerate(args) if value == "--ae"]
    verifier_environment = [args[index + 1] for index, value in enumerate(args) if value == "--ve"]
    for key, value in runtime_env.items():
        assert f"{key}={value}" in agent_environment
        if key == "UV_OFFLINE":
            assert f"{key}={value}" not in verifier_environment
        else:
            assert f"{key}={value}" in verifier_environment
    assert not (run_dir / "harbor-result.json").exists()
    assert not (run_dir / "score").exists()


def test_harbor_single_smoke_forces_one_task_attempt_and_worker() -> None:
    text = _eval_sh("harbor", "fixture")

    assert 'if [ "${EVOLVE_CANDIDATE_SMOKE_MODE:-}" = "single" ]; then' in text


def test_harbor_legacy_cache_mount_matches_adapter_default() -> None:
    text = _eval_sh("harbor", "fixture")

    assert '"target":"/opt/evolve/uv/cache"' in text
    assert '"target":"/installed-agent/uv-cache"' not in text


def test_harbor_rejects_malformed_candidate_runtime_before_launch(tmp_path: Path) -> None:
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
    _write_fake_uv(fake_bin)
    harbor_called = tmp_path / "harbor-called"
    _write_executable(fake_bin / "harbor", f"#!/bin/sh\ntouch {harbor_called}\n")
    run_dir = tmp_path / "run"
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "EVOLVE_RUN_DIR": str(run_dir),
        "EVOLVE_ATTEMPT_ID": "bad-runtime",
        "EVOLVE_FRAMEWORK_PYTHON": sys.executable,
        "EVOLVE_CANDIDATE_RUNTIME_ENV_JSON": "[]",
        "EVOLVE_CANDIDATE_RUNTIME_MOUNTS_JSON": '{"not":"mounts"}',
    }

    result = subprocess.run(
        [str(evaluator / "eval.sh")],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 3
    assert (run_dir / "status").read_text().strip() == "infra_failed"
    assert not harbor_called.exists()


def test_harbor_retry_excludes_only_non_retryable_trial_failures() -> None:
    text = _eval_sh("harbor", "fixture")

    assert "--retry-exclude AgentTimeoutError" in text
    assert "--retry-exclude EvolveCandidateInvalidError" in text
    assert "--retry-exclude ApiUsageLimitError" in text
    assert "retry-exclude VerifierTimeoutError" not in text


def test_score_parser_accepts_complete_final_vector_after_nonzero_harbor_exit(tmp_path: Path) -> None:
    evaluator = tmp_path / "evaluator"
    evaluator.mkdir()
    _write_evaluator_helpers(evaluator)
    (evaluator / "eval.env").write_text("EVOLVE_HARBOR_EXPECTED_TRIALS=2\nEVOLVE_HARBOR_ATTEMPTS=1\n")
    jobs = tmp_path / "jobs"
    job = jobs / "job"
    job.mkdir(parents=True)
    (job / "config.json").write_text(
        json.dumps({"retry": {"max_retries": 1, "exclude_exceptions": ["AgentTimeoutError"]}})
    )
    (job / "timeout").mkdir()
    (job / "timeout" / "result.json").write_text(
        json.dumps(
            {
                "task_name": "case-a",
                "trial_name": "one",
                "agent_result": {"cost_usd": 0},
                "exception_info": {"exception_type": "VerifierTimeoutError", "exception_message": "late"},
            }
        )
    )
    (job / "success").mkdir()
    (job / "success" / "result.json").write_text(
        json.dumps(
            {
                "task_name": "case-b",
                "trial_name": "one",
                "verifier_result": {"rewards": {"reward": 1.0}},
            }
        )
    )
    run_dir = tmp_path / "run"

    result = subprocess.run(
        [sys.executable, str(evaluator / "parse_score.py"), str(jobs), str(run_dir), "7"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert (run_dir / "status").read_text().strip() == "complete"
    metrics = json.loads((run_dir / "metrics.json").read_text())["dimensions"]
    assert metrics["harbor_rc"] == 7
    assert metrics["completed_trials"] == 2


def test_harbor_shell_uses_canonical_parser_result() -> None:
    text = _eval_sh("harbor", "fixture")

    assert '[ "$harbor_rc" -eq 0 ] || exit 3' not in text
    assert 'exit "$parser_rc"' in text
