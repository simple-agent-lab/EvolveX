import importlib.util
import json
import random
from pathlib import Path

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ctx(workspace: Path, run_dir: Path) -> OperatorContext:
    return OperatorContext(
        workspace=workspace,
        checkout=workspace,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={},
        rng=random.Random(0),
    )


def _checkout(tmp_path: Path) -> tuple[Path, Path]:
    checkout = tmp_path / "checkout"
    run_dir = checkout / "runs" / "gen-1"
    (checkout / "operators").mkdir(parents=True)
    (checkout / "target" / "pkg").mkdir(parents=True)
    (checkout / "operators" / "mutate.py").write_text("VALUE = 1\n")
    (checkout / "target" / "agent.py").write_text("def run():\n    return 'ok'\n")
    (checkout / "target" / "pkg" / "helper.py").write_text("HELPER = True\n")
    return checkout, run_dir


def test_hyperagents_validator_accepts_mutate_and_target_python(tmp_path: Path) -> None:
    module = _load_module(
        "hyperagents_validate_under_test",
        ROOT / "library" / "validate" / "hyperagents.py",
    )
    checkout, run_dir = _checkout(tmp_path)

    result = module.HyperAgentsValidate().validate(checkout, _ctx(checkout, run_dir))

    assert result.accept is True
    assert result.reason == "meta-agent and task-agent Python compile"
    assert result.artifacts == ["validate/compile.log"]
    assert "PASS operators/mutate.py" in (run_dir / "validate" / "compile.log").read_text()
    assert "PASS target/agent.py" in (run_dir / "validate" / "compile.log").read_text()


def test_hyperagents_validator_rejects_broken_target_python_and_writes_log(tmp_path: Path) -> None:
    module = _load_module(
        "hyperagents_validate_under_test_broken",
        ROOT / "library" / "validate" / "hyperagents.py",
    )
    checkout, run_dir = _checkout(tmp_path)
    (checkout / "target" / "broken.py").write_text("def broken(:\n")

    result = module.HyperAgentsValidate().validate(checkout, _ctx(checkout, run_dir))

    assert result.accept is False
    assert result.reason == "compile failed for target/broken.py"
    log = run_dir / "validate" / "compile.log"
    assert log.is_file()
    assert "FAIL target/broken.py" in log.read_text()


def test_hyperagents_record_writes_compact_experience_and_archive_pointer(tmp_path: Path) -> None:
    module = _load_module(
        "hyperagents_record_under_test",
        ROOT / "library" / "record" / "hyperagents.py",
    )
    checkout, run_dir = _checkout(tmp_path)
    child = {
        "genid": "1",
        "parent": "0",
        "score": 0.5,
        "status": "complete",
        "reason": "not part of compact experience",
    }

    result = module.HyperAgentsRecord().annotate(child, _ctx(checkout, run_dir))

    assert json.loads((run_dir / "record" / "experience.json").read_text()) == {
        "genid": "1",
        "parent": "0",
        "score": 0.5,
        "status": "complete",
    }
    assert result.fields == {"experience_record": "runs/gen-1/record/experience.json"}
