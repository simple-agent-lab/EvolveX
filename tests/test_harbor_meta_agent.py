import importlib.util
import json
import os
import random
import subprocess
from pathlib import Path

import pytest

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _feedback_guided_meta_agent_module():
    path = ROOT / "library" / "meta_agent" / "feedback_guided.py"
    spec = importlib.util.spec_from_file_location("feedback_guided_harbor_under_test", path)
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
        "surface:\n  include:\n    - target/**\n  exclude: []\n"
        "operators:\n  meta_agent: {variant: feedback_guided, runner: harbor, timeout_s: 30}\n"
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
            "variant": "feedback_guided",
            "runner": "harbor",
            "agent": "codex",
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
if option("--artifact") != "/app/target":
    raise SystemExit("expected /app/target artifact")
if option("--workdir") != "/app":
    raise SystemExit("expected /app workdir")
if option("--agent") != "codex":
    raise SystemExit("expected codex agent")
if option("--model") != "gpt-test":
    raise SystemExit("expected gpt-test model")

source = Path(option("--path", "-p"))
jobs_dir = Path(option("--jobs-dir"))
job_name = option("--job-name")
job_dir = jobs_dir / job_name
trial_dir = job_dir / "task-0001__fake"
artifact = trial_dir / "artifacts" / "app" / "target"
artifact.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, artifact, symlinks=True)

(artifact / "agent.py").write_text("print('child')\\n")
(artifact / "added.txt").write_text("created in Harbor\\n")
(artifact / "obsolete.txt").unlink()
if os.environ.get("FAKE_HARBOR_MODE") == "artifact-symlink":
    (artifact / "link.txt").symlink_to("agent.py")

manifest = [
    {
        "source": "/logs/artifacts",
        "destination": "artifacts/logs/artifacts",
        "type": "directory",
        "status": "empty",
        "service": None,
    },
    {
        "source": "/app/target",
        "destination": "artifacts/app/target",
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
        "name": "codex",
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

    module = _feedback_guided_meta_agent_module()
    result = module.FeedbackGuidedMetaAgent().run(checkout, "failure evidence", _ctx(checkout, run_dir))

    assert (checkout / "target" / "agent.py").read_text() == "print('child')\n"
    assert (checkout / "target" / "added.txt").read_text() == "created in Harbor\n"
    assert not (checkout / "target" / "obsolete.txt").exists()
    assert set(result.changed) == {
        "target/added.txt",
        "target/agent.py",
        "target/obsolete.txt",
    }

    meta_dir = run_dir / "meta_agent"
    assert json.loads((meta_dir / "changed.json").read_text()) == result.changed
    assert json.loads((meta_dir / "predicted_fixes.json").read_text()) == ["task-1"]
    assert json.loads((meta_dir / "surface-check.json").read_text())["ok"] is True
    usage = json.loads((meta_dir / "usage.json").read_text())
    assert usage["usd"] == 0.25
    assert usage["input_tokens"] == 100
    assert usage["cache_tokens"] == 25
    assert usage["output_tokens"] == 10
    assert "diff --git a/target/agent.py b/target/agent.py" in (meta_dir / "patch.diff").read_text()
    assert "variant: feedback_guided" in (meta_dir / "rationale.md").read_text()
    assert "runner: harbor" in (meta_dir / "rationale.md").read_text()
    assert "failure evidence" in (meta_dir / "harbor" / "prompt.md").read_text()
    assert "/app/target" in (meta_dir / "harbor" / "prompt.md").read_text()
    assert list((meta_dir / "harbor" / "jobs").glob("*/*/result.json"))


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

    module = _feedback_guided_meta_agent_module()
    with pytest.raises(SystemExit) as excinfo:
        module.FeedbackGuidedMetaAgent().run(checkout, "failure evidence", _ctx(checkout, run_dir))

    assert excinfo.value.code == 1
    after = {
        path.relative_to(checkout / "target").as_posix(): path.read_bytes()
        for path in (checkout / "target").rglob("*")
        if path.is_file()
    }
    assert after == before
    meta_dir = run_dir / "meta_agent"
    assert json.loads((meta_dir / "changed.json").read_text()) == []
    assert "NonZeroAgentExitCodeError" in (meta_dir / "rationale.md").read_text()


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

    module = _feedback_guided_meta_agent_module()
    with pytest.raises(SystemExit) as excinfo:
        module.FeedbackGuidedMetaAgent().run(checkout, "failure evidence", _ctx(checkout, run_dir))

    assert excinfo.value.code == 1
    assert not marker.exists()
    assert (checkout / "target" / "leak.txt").is_symlink()
    assert "symlink" in (run_dir / "meta_agent" / "rationale.md").read_text().lower()


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

    module = _feedback_guided_meta_agent_module()
    with pytest.raises(SystemExit) as excinfo:
        module.FeedbackGuidedMetaAgent().run(checkout, "failure evidence", _ctx(checkout, run_dir))

    assert excinfo.value.code == 1
    after = {
        path.relative_to(checkout / "target").as_posix(): path.read_bytes()
        for path in (checkout / "target").rglob("*")
        if path.is_file()
    }
    assert after == before
    assert "symlink" in (run_dir / "meta_agent" / "rationale.md").read_text().lower()
