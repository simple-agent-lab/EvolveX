import importlib.util
import json
import os
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from evolve.agent import AgentCommandError
from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]
FILE_TASK_AGENT = "evolve_harbor_agent:FileTaskMiniSweAgent"


def _harbor_runner_module():
    spec = importlib.util.spec_from_file_location(
        "harbor_meta_agent_runner_under_test",
        ROOT / "library" / "meta_agent" / "runners" / "harbor.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_harbor_rejects_oversized_instruction_with_unsafe_agent(tmp_path: Path) -> None:
    runner = _harbor_runner_module()
    prompt = tmp_path / "prompt.md"
    prompt.write_text("x" * (96 * 1024 + 1))

    with pytest.raises(RuntimeError, match="harbor_instruction_transport_unsafe"):
        runner._instruction_transport("mini-swe-agent", prompt)


def test_harbor_accepts_oversized_instruction_with_file_agent(tmp_path: Path) -> None:
    runner = _harbor_runner_module()
    prompt = tmp_path / "prompt.md"
    prompt.write_text("x" * 200_000)

    assert runner._instruction_transport(FILE_TASK_AGENT, prompt) == {
        "bytes": 200_000,
        "mode": "mounted-file",
        "safe": True,
    }


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _checkout(tmp_path: Path) -> tuple[Path, Path]:
    checkout = tmp_path / "checkout"
    run_dir = tmp_path / "runs" / "gen-1"
    (checkout / "target").mkdir(parents=True)
    (checkout / "operators").mkdir()
    (checkout / "target" / "agent.py").write_text("print('parent')\n")
    (checkout / "pyproject.toml").write_text("[project]\nname='test'\nversion='0'\n")
    (checkout / "uv.lock").write_text("version = 1\n")
    (checkout / "target" / "obsolete.txt").write_text("remove me\n")
    (checkout / "operators" / "meta_agent.md").write_text(
        "# Meta-Agent\n\nImprove the target from the supplied failure evidence.\n"
    )
    (checkout / "evolve.yaml").write_text(
        "experiment:\n  id: test\n"
        "target:\n  seed: builtin-dummy\n"
        "surface:\n  include:\n    - target/**\n    - operators/**\n  exclude: []\n"
        "operators:\n  meta_agent: {variant: hyperagents, runner: harbor, timeout_s: 30}\n"
        "evaluator:\n  engine: harbor\n  dataset: pass@k\n"
        "  agent: target.harbor_agent:MiniSweSourceAgent\n"
    )
    _git(checkout, "init", "-q")
    _git(checkout, "config", "user.name", "test")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-qm", "parent")
    _git(checkout, "tag", "gen/0")
    (checkout / "archive.jsonl").write_text('{"genid":"0"}\n')
    evidence = run_dir / "trace_analyzer" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "raw_traces.jsonl").write_text('{"task_name":"task-a"}\n')
    return checkout, run_dir


def _ctx(checkout: Path, run_dir: Path) -> OperatorContext:
    return OperatorContext(
        workspace=checkout,
        checkout=checkout,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={
            "variant": "hyperagents",
            "runner": "harbor",
            "agent": "mini-swe-agent",
            "model": "gpt-test",
            "environment": "docker",
            "timeout_s": 30,
        },
        rng=random.Random(0),
    )


def _install_fake_harbor(bin_dir: Path) -> Path:
    harbor = bin_dir / "harbor"
    harbor.parent.mkdir(parents=True, exist_ok=True)
    harbor.write_text(
        """#!/usr/bin/env python3
import json
import os
import shutil
import sys
from pathlib import Path


def option(*names):
    for name in names:
        if name in sys.argv:
            return sys.argv[sys.argv.index(name) + 1]
    raise SystemExit(f"missing option: {names}")


if len(sys.argv) < 2 or sys.argv[1] != "exec":
    raise SystemExit("expected harbor exec")
if "--no-scan" not in sys.argv:
    raise SystemExit("expected --no-scan")
readonly = os.environ.get("FAKE_HARBOR_MODE") == "readonly"
if readonly:
    if "--artifact" in sys.argv:
        raise SystemExit("readonly execution must not request an artifact")
elif option("--artifact") != "/app/task/workspace":
    raise SystemExit("expected /app/task/workspace artifact")
if option("--workdir") != "/app":
    raise SystemExit("unexpected workdir")
if option("--agent") != "mini-swe-agent":
    raise SystemExit("expected mini-swe-agent")
if option("--model") != "gpt-test":
    raise SystemExit("expected gpt-test model")

source = Path(option("--path", "-p"))
if readonly and not (source / ".evolve-readonly").is_file():
    raise SystemExit("read-only task root must be materialized")
jobs_dir = Path(option("--jobs-dir"))
job_name = option("--job-name")
job_dir = jobs_dir / job_name
trial_dir = job_dir / "task-0001__fake"
trial_dir.mkdir(parents=True, exist_ok=True)
artifact = trial_dir / "artifacts" / "app" / "task" / "workspace"
if not readonly:
    artifact.parent.mkdir(parents=True, exist_ok=True)
    workspace = source / "workspace"
    if not (workspace / ".git").exists():
        raise SystemExit("workspace is missing Git history")
    if not (workspace / "archive.jsonl").is_file():
        raise SystemExit("workspace is missing archive evidence")
    if not (workspace / "runs" / "gen-1" / "trace_analyzer" / "evidence" / "raw_traces.jsonl").is_file():
        raise SystemExit("workspace is missing current trace evidence")
    shutil.copytree(workspace, artifact, symlinks=True)

    (artifact / "target" / "agent.py").write_text("print('child')\\n")
    (artifact / "target" / "added.txt").write_text("created in Harbor\\n")
    (artifact / "target" / "obsolete.txt").unlink()
    if (artifact / "operators").exists():
        (artifact / "operators" / "meta_agent.md").write_text("# Changed by Harbor\\n")
    if os.environ.get("FAKE_HARBOR_MODE") == "artifact-symlink":
        (artifact / "target" / "link.txt").symlink_to("agent.py")
    if os.environ.get("FAKE_HARBOR_MODE") == "protected-edit":
        (artifact / "evolve.yaml").write_text("experiment: {id: compromised}\\n")

manifest = [
    {
        "source": "/logs/artifacts",
        "destination": "artifacts/logs/artifacts",
        "type": "directory",
        "status": "empty",
        "service": None,
    },
    {
        "source": "/app/task/workspace",
        "destination": "artifacts/app/task/workspace",
        "type": "directory",
        "status": "ok",
        "service": None,
    },
]
if readonly:
    report_dir = trial_dir / "artifacts" / "logs" / "artifacts"
    report_dir.mkdir(parents=True)
    (report_dir / "ahe-debugger-response.md").write_text("ROOT CAUSE: collected artifact")
    manifest = [
        {
            "source": "/logs/artifacts",
            "destination": "artifacts/logs/artifacts",
            "type": "directory",
            "status": "ok",
            "service": None,
        }
    ]
(trial_dir / "artifacts" / "manifest.json").write_text(json.dumps(manifest))

exception = None
if os.environ.get("FAKE_HARBOR_MODE") == "agent-error":
    exception = {
        "exception_type": "NonZeroAgentExitCodeError",
        "exception_message": "agent failed",
        "exception_traceback": "omitted",
        "occurred_at": "2026-07-15T00:00:00",
    }

result = {
    "trial_name": "task-0001__fake",
    "agent_info": {
        "name": "mini-swe-agent",
        "version": "fake",
        "model_info": {"name": "gpt-test", "provider": None},
    },
    "exception_info": exception,
    "agent_result": {
        "n_input_tokens": 100,
        "n_cache_tokens": 25,
        "n_output_tokens": 10,
        "cost_usd": 0.25,
    },
    "verifier_result": {"rewards": {"reward": 1.0}},
}
(trial_dir / "result.json").write_text(json.dumps(result))
(job_dir / "result.json").write_text(json.dumps({"stats": {"n_completed_trials": 1}}))

agent_dir = trial_dir / "agent"
agent_dir.mkdir()
(agent_dir / "trajectory.json").write_text(
    json.dumps(
        {
            "steps": [
                {
                    "source": "agent",
                    "message": (
                        "ROOT CAUSE: ignored trajectory"
                        if readonly
                        else 'Completed the mutation.\\npredicted_fixes: ["task-1"]'
                    ),
                }
            ]
        }
    )
)
print(f"Map job written to {job_dir}")
"""
    )
    harbor.chmod(0o755)
    uv = bin_dir / "uv"
    uv.write_text(
        "#!/bin/sh\n"
        '[ -z "${UV_MARKER:-}" ] || printf called > "$UV_MARKER"\n'
        '[ "$1" = run ] || exit 90\nshift\n'
        '[ "$1" = --project ] || exit 91\nshift 2\n'
        '[ "$1" = --frozen ] || exit 92\nshift\n'
        'exec "$@"\n'
    )
    uv.chmod(0o755)
    return harbor


def test_harbor_meta_agent_round_trips_target_and_writes_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, run_dir = _checkout(tmp_path)
    bin_dir = tmp_path / "bin"
    _install_fake_harbor(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    marker = tmp_path / "uv-called"
    monkeypatch.setenv("UV_MARKER", str(marker))

    runner = _harbor_runner_module()
    result = runner.run_agent(checkout, "failure evidence", _ctx(checkout, run_dir))

    assert (checkout / "target" / "agent.py").read_text() == "print('child')\n"
    assert (checkout / "target" / "added.txt").read_text() == "created in Harbor\n"
    assert not (checkout / "target" / "obsolete.txt").exists()
    meta_dir = run_dir / "meta_agent"
    usage = result.usage
    assert usage["usd"] == 0.25
    assert usage["input_tokens"] == 100
    assert usage["cache_tokens"] == 25
    assert usage["output_tokens"] == 10
    assert 'predicted_fixes: ["task-1"]' in result.output
    prompt = (meta_dir / "harbor" / "prompt.md").read_text()
    assert "failure evidence" in prompt
    assert "/app/task/workspace" in prompt
    assert "remove generated virtual environments" in prompt
    assert "/app/candidate" not in prompt
    command = json.loads((meta_dir / "harbor" / "command.json").read_text())
    assert command[command.index("--artifact") + 1] == "/app/task/workspace"
    assert command[command.index("--workdir") + 1] == "/app"
    assert list((meta_dir / "harbor" / "jobs").glob("*/*/result.json"))
    assert marker.read_text() == "called"


def test_harbor_meta_agent_rejects_legacy_pythonpath(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(checkout, run_dir)
    ctx.config["agent_pythonpath"] = "/legacy"

    with pytest.raises(AgentCommandError, match="agent_pythonpath was removed"):
        _harbor_runner_module().run_agent(checkout, "failure evidence", ctx)


def test_harbor_meta_agent_forwards_custom_environment_kwargs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout, run_dir = _checkout(tmp_path)
    bin_dir = tmp_path / "bin"
    _install_fake_harbor(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    ctx = _ctx(checkout, run_dir)
    ctx.config["environment"] = "evolve.harbor_local:LocalEnvironment"
    ctx.config["environment_kwargs"] = {"workdir": "/workspace"}

    _harbor_runner_module().run_agent(checkout, "failure evidence", ctx)

    command = json.loads((run_dir / "meta_agent" / "harbor" / "command.json").read_text())
    assert command[command.index("--env") + 1] == "evolve.harbor_local:LocalEnvironment"
    assert command[command.index("--environment-kwarg") + 1] == 'workdir="/workspace"'


def test_harbor_readonly_agent_returns_response_without_candidate_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, run_dir = _checkout(tmp_path)
    bin_dir = tmp_path / "bin"
    _install_fake_harbor(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_HARBOR_MODE", "readonly")
    runner = _harbor_runner_module()
    output_dir = run_dir / "trace_analyzer" / "debugger" / "task-a" / "attempt-1"

    result = runner.run_readonly_agent(
        checkout,
        "Analyze this trace",
        _ctx(checkout, run_dir),
        output_dir=output_dir,
        job_name="ahe-debug-task-a-attempt-1",
        timeout_s=30,
    )

    assert result.output == "ROOT CAUSE: collected artifact"
    assert result.usage["usd"] == 0.25
    command = json.loads((output_dir / "command.json").read_text())
    assert "--artifact" not in command
    assert not (checkout / "target" / "added.txt").exists()


def test_readonly_artifact_output_rejects_missing_report(tmp_path: Path) -> None:
    trial_dir = tmp_path / "trial"
    artifacts = trial_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "source": "/logs/artifacts",
                    "destination": "artifacts/logs/artifacts",
                    "status": "ok",
                }
            ]
        )
    )

    with pytest.raises(RuntimeError, match="missing AHE debugger report"):
        _harbor_runner_module()._readonly_artifact_output(trial_dir)


def test_readonly_artifact_output_rejects_escape(tmp_path: Path) -> None:
    trial_dir = tmp_path / "trial"
    artifacts = trial_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "manifest.json").write_text(
        json.dumps([{"source": "/logs/artifacts", "destination": "../outside", "status": "ok"}])
    )

    with pytest.raises(RuntimeError, match="escaped the trial"):
        _harbor_runner_module()._readonly_artifact_output(trial_dir)


def test_readonly_artifact_output_rejects_empty_report(tmp_path: Path) -> None:
    trial_dir = tmp_path / "trial"
    report_dir = trial_dir / "artifacts" / "logs" / "artifacts"
    report_dir.mkdir(parents=True)
    (report_dir / "ahe-debugger-response.md").write_text("\n")
    (trial_dir / "artifacts" / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "source": "/logs/artifacts",
                    "destination": "artifacts/logs/artifacts",
                    "status": "ok",
                }
            ]
        )
    )

    with pytest.raises(RuntimeError, match="empty AHE debugger report"):
        _harbor_runner_module()._readonly_artifact_output(trial_dir)


def test_harbor_meta_agent_round_trips_target_and_operators(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout, run_dir = _checkout(tmp_path)
    bin_dir = tmp_path / "bin"
    _install_fake_harbor(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    ctx = _ctx(checkout, run_dir)
    ctx.config["editable_roots"] = ["target", "operators"]
    runner = _harbor_runner_module()
    runner.run_agent(checkout, "failure evidence", ctx)

    assert (checkout / "target" / "agent.py").read_text() == "print('child')\n"
    assert (checkout / "operators" / "meta_agent.md").read_text() == "# Changed by Harbor\n"


def test_harbor_meta_agent_rejects_non_top_level_editable_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(checkout, run_dir)
    ctx.config["editable_roots"] = ["target/src"]
    runner = _harbor_runner_module()

    with pytest.raises(AgentCommandError, match="top-level relative directory"):
        runner.run_agent(checkout, "failure evidence", ctx)


def test_harbor_meta_agent_rejects_protected_workspace_edits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout, run_dir = _checkout(tmp_path)
    before_config = (checkout / "evolve.yaml").read_text()
    before_target = (checkout / "target" / "agent.py").read_text()
    bin_dir = tmp_path / "bin"
    _install_fake_harbor(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_HARBOR_MODE", "protected-edit")

    with pytest.raises(AgentCommandError, match="outside surface"):
        _harbor_runner_module().run_agent(checkout, "failure evidence", _ctx(checkout, run_dir))

    assert (checkout / "evolve.yaml").read_text() == before_config
    assert (checkout / "target" / "agent.py").read_text() == before_target


def test_multi_root_install_rolls_back_when_second_replacement_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, run_dir = _checkout(tmp_path)
    runner = _harbor_runner_module()
    surface = runner.load_surface_policy(checkout)
    bundle = runner._prepare_bundle(checkout, _ctx(checkout, run_dir), ["target", "operators"], surface)
    assert bundle.staging.parent == checkout.parent
    returned = tmp_path / "returned"
    shutil.copytree(bundle.workspace, returned, symlinks=True)
    (returned / "target" / "agent.py").write_text("print('child')\n")
    (returned / "operators" / "meta_agent.md").write_text("# child\n")
    before_target = (checkout / "target" / "agent.py").read_text()
    before_operator = (checkout / "operators" / "meta_agent.md").read_text()
    rename = Path.rename

    def fail_operators(path: Path, target: Path) -> Path:
        if path.as_posix().endswith("replacements/operators"):
            raise OSError("simulated second-root failure")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_operators)
    try:
        with pytest.raises(OSError, match="second-root"):
            runner._install_bundle(checkout, returned, bundle, "gen/0", surface)
        assert (checkout / "target" / "agent.py").read_text() == before_target
        assert (checkout / "operators" / "meta_agent.md").read_text() == before_operator
    finally:
        shutil.rmtree(bundle.staging, ignore_errors=True)


def test_harbor_trial_exception_does_not_modify_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout, run_dir = _checkout(tmp_path)
    before = {
        path.relative_to(checkout / "target").as_posix(): path.read_bytes()
        for path in (checkout / "target").rglob("*")
        if path.is_file()
    }
    bin_dir = tmp_path / "bin"
    _install_fake_harbor(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_HARBOR_MODE", "agent-error")

    runner = _harbor_runner_module()
    with pytest.raises(AgentCommandError) as excinfo:
        runner.run_agent(checkout, "failure evidence", _ctx(checkout, run_dir))

    assert excinfo.value.returncode == 1
    after = {
        path.relative_to(checkout / "target").as_posix(): path.read_bytes()
        for path in (checkout / "target").rglob("*")
        if path.is_file()
    }
    assert after == before
    assert "NonZeroAgentExitCodeError" in str(excinfo.value)
    error = json.loads((run_dir / "meta_agent" / "harbor" / "error.json").read_text())
    assert error["type"] == "RuntimeError"
    assert "NonZeroAgentExitCodeError" in error["message"]


def test_harbor_meta_agent_rejects_source_symlinks_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, run_dir = _checkout(tmp_path)
    (checkout / "outside-secret.txt").write_text("do not upload\n")
    (checkout / "target" / "leak.txt").symlink_to("../outside-secret.txt")
    bin_dir = tmp_path / "bin"
    fake_harbor = _install_fake_harbor(bin_dir)
    marker = tmp_path / "harbor-was-launched"
    fake_harbor.write_text(
        fake_harbor.read_text().replace(
            "if len(sys.argv) < 2",
            f"Path({str(marker)!r}).write_text('yes')\n\nif len(sys.argv) < 2",
        )
    )
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    runner = _harbor_runner_module()
    with pytest.raises(AgentCommandError) as excinfo:
        runner.run_agent(checkout, "failure evidence", _ctx(checkout, run_dir))

    assert excinfo.value.returncode == 1
    assert not marker.exists()
    assert (checkout / "target" / "leak.txt").is_symlink()
    assert "symlink" in str(excinfo.value).lower()


def test_harbor_meta_agent_rejects_returned_symlinks_without_modifying_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, run_dir = _checkout(tmp_path)
    before = {
        path.relative_to(checkout / "target").as_posix(): path.read_bytes()
        for path in (checkout / "target").rglob("*")
        if path.is_file()
    }
    bin_dir = tmp_path / "bin"
    _install_fake_harbor(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_HARBOR_MODE", "artifact-symlink")

    runner = _harbor_runner_module()
    with pytest.raises(AgentCommandError) as excinfo:
        runner.run_agent(checkout, "failure evidence", _ctx(checkout, run_dir))

    assert excinfo.value.returncode == 1
    after = {
        path.relative_to(checkout / "target").as_posix(): path.read_bytes()
        for path in (checkout / "target").rglob("*")
        if path.is_file()
    }
    assert after == before
    assert "symlink" in str(excinfo.value).lower()


def test_install_bundle_omits_ignored_runtime_tree_with_symlinks(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    (checkout / "target" / ".gitignore").write_text(".venv/\n")
    _git(checkout, "add", "target/.gitignore")
    _git(checkout, "commit", "-qm", "ignore runtime environment")
    _git(checkout, "tag", "-f", "gen/0")
    runner = _harbor_runner_module()
    surface = runner.load_surface_policy(checkout)
    bundle = runner._prepare_bundle(checkout, _ctx(checkout, run_dir), ["target"], surface)
    returned = tmp_path / "returned"
    shutil.copytree(bundle.workspace, returned)
    (returned / "target" / "agent.py").write_text("print('child')\n")
    python = returned / "target" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to("/runtime/python")

    try:
        changed = runner._install_bundle(checkout, returned, bundle, "gen/0", surface)
    finally:
        shutil.rmtree(bundle.staging, ignore_errors=True)

    assert changed == ["target/agent.py"]
    assert (checkout / "target" / "agent.py").read_text() == "print('child')\n"
    assert not (checkout / "target" / ".venv").exists()


def test_agent_output_prefers_preserved_model_response_over_post_submit_message(tmp_path: Path) -> None:
    agent = tmp_path / "trial" / "agent"
    agent.mkdir(parents=True)
    (agent / "trajectory.json").write_text(json.dumps({"steps": [{"source": "agent", "message": "submit next"}]}))
    (agent / "mini-swe-agent.trajectory.json").write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "role": "tool",
                        "content": "continue",
                        "extra": {
                            "response": {"choices": [{"message": {"content": "analysis and required manifest"}}]}
                        },
                    }
                ]
            }
        )
    )

    assert _harbor_runner_module()._agent_output(tmp_path / "trial") == "analysis and required manifest"
