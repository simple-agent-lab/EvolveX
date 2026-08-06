from pathlib import Path

import pytest
from harbor.models.registry import DatasetFileInfo, DatasetMetadata
from harbor.models.task.id import GitTaskId, PackageTaskId

from evolve import evaluation as evaluation_package
from evolve import splits as dataset_module


def _task(root: Path, name: str, *, instruction: str = "solve it") -> None:
    task = root / name
    task.mkdir(parents=True)
    (task / "task.toml").write_text(f'[task]\nname = "{name}"\n')
    (task / "instruction.md").write_text(instruction)
    tests = task / "tests"
    tests.mkdir()
    (tests / "test.sh").write_text("#!/bin/sh\nexit 0\n")


def test_local_dataset_identity_is_portable_and_content_backed(tmp_path: Path) -> None:
    first = tmp_path / "host-a" / "tasks"
    second = tmp_path / "different-host" / "renamed-dataset"
    _task(first, "task-a")
    _task(first, "task-b")
    _task(second, "task-a")
    _task(second, "task-b")

    first_identity = evaluation_package.local_dataset_identity(first, ("task-b", "task-a"))
    second_identity = evaluation_package.local_dataset_identity(second, ("task-a", "task-b"))

    assert first_identity == second_identity
    assert first_identity.source == "local"
    assert first_identity.members == ("task-a", "task-b")
    assert first_identity.resolved_reference == f"sha256:{first_identity.digest}"
    assert len(first_identity.digest) == 64

    (second / "task-a" / "instruction.md").write_text("different bytes")

    assert evaluation_package.local_dataset_identity(second, ("task-a", "task-b")).digest != first_identity.digest


def test_local_dataset_identity_hashes_only_selected_members(tmp_path: Path) -> None:
    dataset = tmp_path / "tasks"
    _task(dataset, "selected")
    _task(dataset, "not-selected")

    before = evaluation_package.local_dataset_identity(dataset, ("selected",))
    (dataset / "not-selected" / "instruction.md").write_text("changed outside selection")
    after = evaluation_package.local_dataset_identity(dataset, ("selected",))

    assert after == before


def test_local_dataset_identity_reuses_per_task_digests(tmp_path: Path) -> None:
    dataset = tmp_path / "tasks"
    _task(dataset, "task-a")
    _task(dataset, "task-b")

    identity = evaluation_package.local_dataset_identity(dataset, ("task-b", "task-a"))

    assert identity.task_digest_map() == {
        "task-a": dataset_module.local_task_content_digest(dataset, "task-a"),
        "task-b": dataset_module.local_task_content_digest(dataset, "task-b"),
    }


def test_local_dataset_identity_includes_executable_permissions(tmp_path: Path) -> None:
    dataset = tmp_path / "tasks"
    _task(dataset, "task-a")
    verifier = dataset / "task-a" / "tests" / "test.sh"
    verifier.chmod(0o644)
    before = evaluation_package.local_dataset_identity(dataset, ("task-a",))

    verifier.chmod(0o755)
    after = evaluation_package.local_dataset_identity(dataset, ("task-a",))

    assert after.digest != before.digest


def test_local_dataset_identity_rejects_symlinks_that_escape_a_task(tmp_path: Path) -> None:
    dataset = tmp_path / "tasks"
    _task(dataset, "task-a")
    outside = tmp_path / "outside-secret"
    outside.write_text("host-specific")
    (dataset / "task-a" / "outside-link").symlink_to(outside)

    with pytest.raises(ValueError, match="symlink escapes selected task"):
        evaluation_package.local_dataset_identity(dataset, ("task-a",))


def test_selected_dataset_identity_uses_only_frozen_selected_task_digests() -> None:
    manifest = {
        "identity_status": "verified",
        "dataset_identity": {
            "source": "local",
            "digest": "f" * 64,
            "resolved_reference": f"sha256:{'f' * 64}",
        },
        "task_digests": {"task-a": "a" * 64, "task-b": "b" * 64, "task-c": "c" * 64},
    }

    first = evaluation_package.selected_dataset_identity(manifest, ("task-b", "task-a"))
    reordered = evaluation_package.selected_dataset_identity(manifest, ("task-a", "task-b"))
    changed_unselected = evaluation_package.selected_dataset_identity(
        {**manifest, "task_digests": {**manifest["task_digests"], "task-c": "d" * 64}},
        ("task-a", "task-b"),
    )
    changed_selected = evaluation_package.selected_dataset_identity(
        {**manifest, "task_digests": {**manifest["task_digests"], "task-b": "e" * 64}},
        ("task-a", "task-b"),
    )

    assert first == reordered == changed_unselected
    assert first.members == ("task-a", "task-b")
    assert changed_selected.digest != first.digest


class _RegistryClient:
    def __init__(self, metadata: DatasetMetadata):
        self.metadata = metadata

    async def get_dataset_metadata(self, _name: str) -> DatasetMetadata:
        return self.metadata


def _registry_metadata(*, commit: str = "a" * 40, content_hash: str = "b" * 64) -> DatasetMetadata:
    return DatasetMetadata(
        name="swe-bench-lite",
        version="1.0",
        description="ignored human description",
        task_ids=[
            GitTaskId(
                git_url="https://example.invalid/tasks.git",
                git_commit_id=commit,
                path=Path("tasks/task-a"),
            ),
            PackageTaskId(org="bench", name="task-b", ref=f"sha256:{'c' * 64}"),
        ],
        files=[DatasetFileInfo(path="metric.py", storage_path="private/path", content_hash=f"sha256:{'d' * 64}")],
        dataset_version_content_hash=content_hash,
    )


def test_registry_dataset_identity_uses_resolved_immutable_metadata() -> None:
    first = evaluation_package.registry_dataset_identity("swe-bench-lite", client=_RegistryClient(_registry_metadata()))
    changed_commit = evaluation_package.registry_dataset_identity(
        "swe-bench-lite", client=_RegistryClient(_registry_metadata(commit="e" * 40))
    )
    changed_dataset = evaluation_package.registry_dataset_identity(
        "swe-bench-lite", client=_RegistryClient(_registry_metadata(content_hash="f" * 64))
    )

    assert first.source == "registry"
    assert first.resolved_reference == "swe-bench-lite@1.0"
    assert first.members == ("bench/task-b", "task-a")
    assert len(first.digest) == 64
    assert set(first.task_digest_map()) == {"bench/task-b", "task-a"}
    assert all(len(digest) == 64 for digest in first.task_digest_map().values())
    assert changed_commit.digest != first.digest
    assert changed_dataset.digest != first.digest


@pytest.mark.parametrize(
    "task_id",
    [
        GitTaskId(git_url="https://example.invalid/tasks.git", git_commit_id=None, path=Path("tasks/task-a")),
        PackageTaskId(org="bench", name="task-b", ref="latest"),
    ],
)
def test_registry_dataset_identity_rejects_unpinned_task_references(task_id: object) -> None:
    metadata = DatasetMetadata(name="dataset", version="1", task_ids=[task_id])

    with pytest.raises(ValueError, match="immutable task reference"):
        evaluation_package.registry_dataset_identity("dataset", client=_RegistryClient(metadata))
