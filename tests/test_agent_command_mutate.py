import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _agent_command_mutate_cls():
    spec = importlib.util.spec_from_file_location(
        "agent_command_under_test",
        ROOT / "library" / "mutate" / "agent_command.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AgentCommandMutate


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _checkout(tmp_path: Path) -> tuple[Path, Path]:
    checkout = tmp_path / "checkout"
    run_dir = tmp_path / "runs" / "gen-1"
    (checkout / "target").mkdir(parents=True)
    (checkout / "operators").mkdir()
    (checkout / "target" / "agent.py").write_text("print('parent')\n")
    (checkout / "README.md").write_text("parent\n")
    (checkout / "operators" / "mutate.md").write_text("# Mutate\n\nImprove the target.\n")
    (checkout / "evolve.yaml").write_text(
        "experiment:\n  id: test\n"
        "target:\n  seed: builtin-dummy\n"
        "surface:\n  include:\n    - target/**\n  exclude: []\n"
        "operators:\n  mutate: {timeout_s: 30}\n"
        "evaluator:\n  engine: harbor\n  dataset: pass@k\n  agent: target.harbor_agent:MiniSweSourceAgent\n"
    )
    _git(checkout, "init", "-q")
    _git(checkout, "config", "user.name", "test")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-qm", "parent")
    _git(checkout, "tag", "gen/0")
    return checkout, run_dir


def _ctx(checkout: Path, run_dir: Path, command: str) -> OperatorContext:
    return OperatorContext(
        workspace=checkout,
        checkout=checkout,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={"command": command, "timeout_s": 30},
        rng=random.Random(0),
    )


def test_agent_command_mutate_runs_meta_agent_and_writes_artifacts(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    script = tmp_path / "agent.py"
    script.write_text(
        "from pathlib import Path\n"
        "Path('target/agent.py').write_text(\"print('child')\\n\")\n"
        "print('predicted_fixes: [\"task-1\"]')\n"
    )

    result = _agent_command_mutate_cls()().mutate(checkout, "", _ctx(checkout, run_dir, f"{sys.executable} {script}"))

    assert result.changed == ["target/agent.py"]
    assert json.loads((run_dir / "mutate" / "changed.json").read_text()) == ["target/agent.py"]
    assert json.loads((run_dir / "mutate" / "predicted_fixes.json").read_text()) == ["task-1"]
    assert json.loads((run_dir / "mutate" / "surface-check.json").read_text())["ok"] is True
    assert json.loads((run_dir / "mutate" / "usage.json").read_text())["usd"] == 0
    patch_diff = (run_dir / "mutate" / "patch.diff").read_text()
    assert "diff --git a/target/agent.py b/target/agent.py" in patch_diff
    assert "+print('child')" in patch_diff
    rationale = (run_dir / "mutate" / "rationale.md").read_text()
    assert "written-by: operators/mutate.py" in rationale
    assert "variant: agent_command" in rationale


def test_agent_command_mutate_exits_nonzero_after_writing_failure_artifacts(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    script = tmp_path / "agent.py"
    script.write_text("import sys\nprint('bad')\nsys.exit(7)\n")

    try:
        _agent_command_mutate_cls()().mutate(checkout, "", _ctx(checkout, run_dir, f"{sys.executable} {script}"))
    except SystemExit as exc:
        assert exc.code == 7
    else:
        raise AssertionError("expected SystemExit")

    assert json.loads((run_dir / "mutate" / "changed.json").read_text()) == []
    assert (run_dir / "mutate" / "patch.diff").is_file()
    assert "error:" in (run_dir / "mutate" / "rationale.md").read_text()


def test_agent_command_mutate_repairs_surface_violation(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    script = tmp_path / "agent.py"
    script.write_text("from pathlib import Path\nPath('README.md').write_text('leak\\n')\n")

    result = _agent_command_mutate_cls()().mutate(checkout, "", _ctx(checkout, run_dir, f"{sys.executable} {script}"))

    assert result.changed == []
    surface = json.loads((run_dir / "mutate" / "surface-check.json").read_text())
    assert surface == {"ok": True, "mutated": [], "violations": []}
    assert "repaired surface violations" in (run_dir / "mutate" / "rationale.md").read_text()
    assert (checkout / "README.md").read_text() == "parent\n"


def test_agent_command_mutate_writes_artifacts_for_prompt_failure(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    (checkout / "operators" / "mutate.md").unlink()
    script = tmp_path / "agent.py"
    script.write_text("raise SystemExit('should not run')\n")

    try:
        _agent_command_mutate_cls()().mutate(checkout, "", _ctx(checkout, run_dir, f"{sys.executable} {script}"))
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit")

    assert json.loads((run_dir / "mutate" / "changed.json").read_text()) == []
    assert json.loads((run_dir / "mutate" / "usage.json").read_text())["usd"] == 0
    surface = json.loads((run_dir / "mutate" / "surface-check.json").read_text())
    assert surface["ok"] is True
    rationale = (run_dir / "mutate" / "rationale.md").read_text()
    assert "error: FileNotFoundError" in rationale
