from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from evolve.splits import task_content_digests

ROOT = Path(__file__).resolve().parents[1]
PREPARER = ROOT / "scripts" / "examples" / "terminal_bench_smoke" / "prepare_dataset.py"


def _load_preparer():
    spec = importlib.util.spec_from_file_location("terminal_bench_2_prepare", PREPARER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _task(root: Path, name: str, instruction: str) -> Path:
    task = root / name
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "task.toml").write_text(f'[metadata]\nname = "{name}"\n')
    (task / "instruction.md").write_text(instruction)
    (task / "environment" / "Dockerfile").write_text("FROM scratch\n")
    (task / "tests" / "test.sh").write_text("exit 0\n")
    return task


def _manifest(path: Path, source: Path, names: list[str]) -> Path:
    observed = task_content_digests(source)
    path.write_text(
        json.dumps(
            {
                "dataset": "terminal-bench@2.0",
                "name": "terminal-bench-2-30-v1",
                "selection": {"count": len(names), "scheme": "test", "seed": "fixed"},
                "tasks": {name: "sha256:" + observed[name] for name in names},
                "version": 1,
            }
        )
    )
    return path


def test_preparer_materializes_manifest_tasks_and_source_receipt(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "raw" / "terminal-bench"
    _task(source, "task-a", "A\n")
    _task(source, "task-b", "B\n")
    _task(source, "not-selected", "extra source task\n")
    manifest = _manifest(tmp_path / "manifest.json", source, ["task-a", "task-b"])
    destination = tmp_path / "prepared"
    module = _load_preparer()
    monkeypatch.setattr(module, "MANIFEST_PATH", manifest)

    assert module.main([str(source.parent), str(destination)]) == 0

    assert sorted(path.name for path in destination.iterdir()) == ["dataset-source.json", "task-a", "task-b"]
    assert json.loads((destination / "dataset-source.json").read_text()) == {
        "dataset": "terminal-bench@2.0",
        "manifest": "terminal-bench-2-30-v1",
        "selection": {"count": 2, "scheme": "test", "seed": "fixed"},
    }


def test_preparer_reuses_a_verified_existing_destination(tmp_path: Path, monkeypatch, capsys) -> None:
    source = tmp_path / "raw"
    _task(source, "task-a", "A\n")
    manifest = _manifest(tmp_path / "manifest.json", source, ["task-a"])
    destination = tmp_path / "prepared"
    module = _load_preparer()
    monkeypatch.setattr(module, "MANIFEST_PATH", manifest)

    assert module.main([str(source), str(destination)]) == 0
    assert module.main([str(source), str(destination)]) == 0

    assert "Reused verified dataset" in capsys.readouterr().out


def test_preparer_rejects_missing_manifest_tasks(tmp_path: Path, monkeypatch) -> None:
    complete = tmp_path / "complete"
    _task(complete, "task-a", "A\n")
    _task(complete, "task-b", "B\n")
    manifest = _manifest(tmp_path / "manifest.json", complete, ["task-a", "task-b"])
    incomplete = tmp_path / "incomplete"
    _task(incomplete, "task-a", "A\n")
    module = _load_preparer()
    monkeypatch.setattr(module, "MANIFEST_PATH", manifest)

    with pytest.raises(SystemExit, match="missing=task-b"):
        module.main([str(incomplete), str(tmp_path / "prepared")])


def test_preparer_never_overwrites_a_mismatched_destination(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "raw"
    _task(source, "task-a", "A\n")
    manifest = _manifest(tmp_path / "manifest.json", source, ["task-a"])
    destination = tmp_path / "prepared"
    _task(destination, "task-a", "changed\n")
    sentinel = destination / "keep-me"
    sentinel.write_text("present\n")
    module = _load_preparer()
    monkeypatch.setattr(module, "MANIFEST_PATH", manifest)

    with pytest.raises(SystemExit, match="existing destination does not match"):
        module.main([str(source), str(destination)])

    assert sentinel.read_text() == "present\n"


def test_checked_in_manifest_digests_normalize_to_task_content_identity() -> None:
    module = _load_preparer()

    expected = module._expected_tasks(module._manifest())

    assert len(expected) == 30
    assert all(len(digest) == 64 and not digest.startswith("sha256:") for digest in expected.values())
