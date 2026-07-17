import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evolve.patching import SurfacePolicy
from library.meta_agent.runners.editable_bundle import (
    cleanup_editable_bundle,
    install_returned_bundle,
    prepare_editable_bundle,
)


def _git(root: Path, *args: str) -> None:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    for name in ("target", "operators", "evaluator"):
        (root / name).mkdir(parents=True)
        (root / name / "value.txt").write_text(f"parent {name}\n")
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "test")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "parent")
    _git(root, "tag", "gen/0")
    return root


def _surface(*roots: str) -> SurfacePolicy:
    return SurfacePolicy(include=[f"{root}/**" for root in roots], exclude=[])


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


@pytest.mark.parametrize("roots", [["target"], ["target", "operators"]])
def test_prepare_editable_bundle_preserves_repository_paths(tmp_path: Path, roots: list[str]) -> None:
    checkout = _checkout(tmp_path)
    bundle = prepare_editable_bundle(checkout, roots, _surface("target", "operators"))
    try:
        assert [path.as_posix() for path in bundle.roots] == roots
        for root in roots:
            assert (bundle.task_root / "candidate" / root / "value.txt").exists()
    finally:
        cleanup_editable_bundle(bundle)


@pytest.mark.parametrize(
    ("roots", "message"),
    [
        ([], "at least one editable root"),
        (["/target"], "must be relative"),
        (["../target"], "must not escape"),
        (["target", "target/src"], "must not overlap"),
        (["evaluator"], "not covered by mutable surface"),
    ],
)
def test_prepare_rejects_invalid_roots(tmp_path: Path, roots: list[str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        prepare_editable_bundle(_checkout(tmp_path), roots, _surface("target", "operators"))


def test_install_replaces_two_roots(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    surface = _surface("target", "operators")
    bundle = prepare_editable_bundle(checkout, ["target", "operators"], surface)
    try:
        returned = tmp_path / "returned"
        (returned / "target").mkdir(parents=True)
        (returned / "operators").mkdir()
        (returned / "target" / "value.txt").write_text("child target\n")
        (returned / "operators" / "value.txt").write_text("child operators\n")
        changed = install_returned_bundle(checkout, returned, bundle, "gen/0", surface)
        assert changed == ["operators/value.txt", "target/value.txt"]
        assert (checkout / "target" / "value.txt").read_text() == "child target\n"
        assert (checkout / "operators" / "value.txt").read_text() == "child operators\n"
    finally:
        cleanup_editable_bundle(bundle)


@pytest.mark.parametrize("mode", ["missing", "unexpected", "symlink", "bad-diff"])
def test_failed_install_preserves_all_live_roots(tmp_path: Path, mode: str) -> None:
    checkout = _checkout(tmp_path)
    surface = _surface("target", "operators")
    before = {root: _snapshot(checkout / root) for root in ("target", "operators")}
    bundle = prepare_editable_bundle(checkout, ["target", "operators"], surface)
    returned = tmp_path / "returned"
    for root in ("target", "operators"):
        (returned / root).mkdir(parents=True)
        (returned / root / "value.txt").write_text(f"child {root}\n")
    if mode == "missing":
        (returned / "operators" / "value.txt").unlink()
        (returned / "operators").rmdir()
    elif mode == "unexpected":
        (returned / "other").mkdir()
    elif mode == "symlink":
        (returned / "target" / "link").symlink_to("value.txt")
    else:
        (returned / "target" / "value.txt").write_text("trailing space \n")
    try:
        with pytest.raises(RuntimeError):
            install_returned_bundle(checkout, returned, bundle, "gen/0", surface)
        assert _snapshot(checkout / "target") == before["target"]
        assert _snapshot(checkout / "operators") == before["operators"]
    finally:
        cleanup_editable_bundle(bundle)


def test_second_root_rename_failure_rolls_back_first_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = _checkout(tmp_path)
    surface = _surface("target", "operators")
    before = {root: _snapshot(checkout / root) for root in ("target", "operators")}
    bundle = prepare_editable_bundle(checkout, ["target", "operators"], surface)
    returned = tmp_path / "returned"
    for root in ("target", "operators"):
        (returned / root).mkdir(parents=True)
        (returned / root / "value.txt").write_text(f"child {root}\n")
    original = Path.rename

    def fail_second_replacement(path: Path, target: Path) -> Path:
        if "replacements/operators" in path.as_posix():
            raise OSError("simulated rename failure")
        return original(path, target)

    monkeypatch.setattr(Path, "rename", fail_second_replacement)
    try:
        with pytest.raises(OSError, match="simulated"):
            install_returned_bundle(checkout, returned, bundle, "gen/0", surface)
        assert _snapshot(checkout / "target") == before["target"]
        assert _snapshot(checkout / "operators") == before["operators"]
    finally:
        cleanup_editable_bundle(bundle)
