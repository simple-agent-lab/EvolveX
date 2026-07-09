import subprocess
from pathlib import Path

from evolve.mutation import SurfacePolicy, create_mutation_patch


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "test")
    _git(root, "config", "user.email", "test@example.invalid")
    (root / "target").mkdir()
    (root / "target" / "agent.py").write_text("print('parent')\n")
    (root / "README.md").write_text("parent\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "parent")
    _git(root, "tag", "gen/0")
    return root


def test_create_mutation_patch_reports_changed_paths_and_diff(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "target" / "agent.py").write_text("print('child')\n")

    patch = create_mutation_patch(
        checkout=root,
        parent_ref="gen/0",
        surface=SurfacePolicy(include=["target/**"], exclude=[]),
    )

    assert patch.changed_paths == ["target/agent.py"]
    assert patch.surface_report == {"ok": True, "mutated": ["target/agent.py"], "violations": []}
    assert "+print('child')" in patch.diff
    assert patch.notes == []


def test_create_mutation_patch_repairs_out_of_surface_paths(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "target" / "agent.py").write_text("print('child')\n")
    (root / "README.md").write_text("leak\n")

    patch = create_mutation_patch(
        checkout=root,
        parent_ref="gen/0",
        surface=SurfacePolicy(include=["target/**"], exclude=[]),
    )

    assert patch.changed_paths == ["target/agent.py"]
    assert patch.surface_report == {"ok": True, "mutated": ["target/agent.py"], "violations": []}
    assert "README.md" not in patch.diff
    assert (root / "README.md").read_text() == "parent\n"
    assert patch.notes == ["repaired surface violations by reverted: README.md"]


def test_create_mutation_patch_reports_remaining_violation_when_repair_disabled(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "README.md").write_text("leak\n")

    patch = create_mutation_patch(
        checkout=root,
        parent_ref="gen/0",
        surface=SurfacePolicy(include=["target/**"], exclude=[]),
        repair=False,
    )

    assert patch.changed_paths == ["README.md"]
    assert patch.surface_report == {"ok": False, "mutated": ["README.md"], "violations": ["README.md"]}
    assert patch.notes == []
