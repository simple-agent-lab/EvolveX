import importlib.util
import os
import random
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
if option("--artifact") != "/app/candidate":
    raise SystemExit("expected /app/candidate artifact")
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
artifact = trial_dir / "artifacts" / "app" / "candidate"
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
        "source": "/app/candidate",
        "destination": "artifacts/app/candidate",
        "type": "directory",
        "status": "ok",
        "service": None,
    },
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
                    "message": 'Completed the mutation.\\npredicted_fixes: ["task-1"]',
                }
            ]
        }
    )
)
print(f"Map job written to {job_dir}")
"""
    )
    harbor.chmod(0o755)
    return harbor


def test_harbor_meta_agent_round_trips_target_and_writes_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, run_dir = _checkout(tmp_path)
    bin_dir = tmp_path / "bin"
    _install_fake_harbor(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

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
    assert "/app/candidate" in (meta_dir / "harbor" / "prompt.md").read_text()
    assert list((meta_dir / "harbor" / "jobs").glob("*/*/result.json"))


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
