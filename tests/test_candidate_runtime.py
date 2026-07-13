from pathlib import Path

import pytest
from conftest import write_locked_miniswe_seed

from evolve.candidate_runtime import CandidateDependencyError, validate_miniswe_candidate


def _checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    write_locked_miniswe_seed(checkout / "target")
    return checkout


def test_validate_rejects_missing_lock(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    (checkout / "target" / "uv.lock").unlink()

    with pytest.raises(CandidateDependencyError) as exc:
        validate_miniswe_candidate(checkout)

    assert exc.value.code == "lock_missing"


def test_validate_rejects_project_change_without_lock_change(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    project = checkout / "target" / "pyproject.toml"
    project.write_text(project.read_text().replace("dependencies = []", "dependencies = ['idna']"))

    with pytest.raises(CandidateDependencyError) as exc:
        validate_miniswe_candidate(checkout, changed_paths=["target/pyproject.toml"])

    assert exc.value.code == "project_changed_without_lock"


def test_validate_rejects_incompatible_lock_without_mutating_it(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    project = checkout / "target" / "pyproject.toml"
    lock = checkout / "target" / "uv.lock"
    project.write_text(project.read_text().replace("dependencies = []", "dependencies = ['idna']"))
    before = lock.read_bytes()

    with pytest.raises(CandidateDependencyError) as exc:
        validate_miniswe_candidate(
            checkout,
            changed_paths=["target/pyproject.toml", "target/uv.lock"],
        )

    assert exc.value.code == "lock_incompatible"
    assert lock.read_bytes() == before


def test_validate_accepts_compatible_lock_only_update(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    lock = checkout / "target" / "uv.lock"
    lock.write_text(lock.read_text() + "\n# reviewed\n")

    identity = validate_miniswe_candidate(checkout, changed_paths=["target/uv.lock"])

    assert len(identity.digest) == 64
