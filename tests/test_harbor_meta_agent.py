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


def _harbor_runner_module():
    spec = importlib.util.spec_from_file_location(
        "harbor_meta_agent_runner_under_test",
        ROOT / "library" / "meta_agent" / "runners" / "harbor.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
elif option("--artifact") != "/app/task/candidate":
    raise SystemExit("expected /app/task/candidate artifact")
if option("--workdir") != "/app":
    raise SystemExit("expected /app workdir")
if option("--agent") != "mini-swe-agent":
    raise SystemExit("expected mini-swe-agent")
if option("--model") != "gpt-test":
    raise SystemExit("expected gpt-test model")

source = Path(option("--path", "-p"))
jobs_dir = Path(option("--jobs-dir"))
job_name = option("--job-name")
job_dir = jobs_dir / job_name
trial_dir = job_dir / "task-0001__fake"
trial_dir.mkdir(parents=True, exist_ok=True)
artifact = trial_dir / "artifacts" / "app" / "task" / "candidate"
if not readonly:
    artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / "candidate", artifact, symlinks=True)

    (artifact / "target" / "agent.py").write_text("print('child')\\n")
    (artifact / "target" / "added.txt").write_text("created in Harbor\\n")
    (artifact / "target" / "obsolete.txt").unlink()
    if (artifact / "operators").exists():
        (artifact / "operators" / "meta_agent.md").write_text("# Changed by Harbor\\n")
    if os.environ.get("FAKE_HARBOR_MODE") == "artifact-symlink":
        (artifact / "target" / "link.txt").symlink_to("agent.py")

manifest = [
    {
        "source": "/logs/artifacts",
        "destination": "artifacts/logs/artifacts",
        "type": "directory",
        "status": "empty",
        "service": None,
    },
    {
        "source": "/app/task/candidate",
        "destination": "artifacts/app/task/candidate",
        "type": "directory",
        "status": "ok",
        "service": None,
    },
]
if not readonly:
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
                        "ROOT CAUSE: tool retry loop"
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
    assert "failure evidence" in (meta_dir / "harbor" / "prompt.md").read_text()
    assert "/app/task/candidate" in (meta_dir / "harbor" / "prompt.md").read_text()
    assert list((meta_dir / "harbor" / "jobs").glob("*/*/result.json"))
    assert marker.read_text() == "called"


def test_harbor_meta_agent_rejects_legacy_pythonpath(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(checkout, run_dir)
    ctx.config["agent_pythonpath"] = "/legacy"

    with pytest.raises(AgentCommandError, match="agent_pythonpath was removed"):
        _harbor_runner_module().run_agent(checkout, "failure evidence", ctx)


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

    assert result.output == "ROOT CAUSE: tool retry loop"
    assert result.usage["usd"] == 0.25
    command = json.loads((output_dir / "command.json").read_text())
    assert "--artifact" not in command
    assert not (checkout / "target" / "added.txt").exists()


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


def test_multi_root_install_rolls_back_when_second_replacement_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, _run_dir = _checkout(tmp_path)
    runner = _harbor_runner_module()
    surface = runner.load_surface_policy(checkout)
    bundle = runner._prepare_bundle(checkout, ["target", "operators"], surface)
    returned = tmp_path / "returned"
    shutil.copytree(checkout / "target", returned / "target")
    shutil.copytree(checkout / "operators", returned / "operators")
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
    checkout, _run_dir = _checkout(tmp_path)
    (checkout / "target" / ".gitignore").write_text(".venv/\n")
    _git(checkout, "add", "target/.gitignore")
    _git(checkout, "commit", "-qm", "ignore runtime environment")
    _git(checkout, "tag", "-f", "gen/0")
    runner = _harbor_runner_module()
    surface = runner.load_surface_policy(checkout)
    bundle = runner._prepare_bundle(checkout, ["target"], surface)
    returned = tmp_path / "returned"
    shutil.copytree(checkout / "target", returned / "target")
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
    (agent / "trajectory.json").write_text(
        json.dumps({"steps": [{"source": "agent", "message": "submit next"}]})
    )
    (agent / "mini-swe-agent.trajectory.json").write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "role": "tool",
                        "content": "continue",
                        "extra": {
                            "response": {
                                "choices": [{"message": {"content": "analysis and required manifest"}}]
                            }
                        },
                    }
                ]
            }
        )
    )

    assert _harbor_runner_module()._agent_output(tmp_path / "trial") == "analysis and required manifest"
