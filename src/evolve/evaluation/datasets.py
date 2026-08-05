from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from harbor.models.registry import DatasetMetadata
from harbor.models.task.id import GitTaskId, PackageTaskId
from harbor.registry.client.factory import RegistryClientFactory

_GIT_COMMIT = re.compile(r"[0-9a-fA-F]{40}")
_SHA256_REF = re.compile(r"sha256:[0-9a-fA-F]{64}")


@dataclass(frozen=True)
class DatasetContentIdentity:
    source: str
    digest: str
    members: tuple[str, ...]
    resolved_reference: str
    task_digests: tuple[tuple[str, str], ...]

    def task_digest_map(self) -> dict[str, str]:
        return dict(self.task_digests)


class RegistryMetadataClient(Protocol):
    async def get_dataset_metadata(self, name: str) -> DatasetMetadata: ...


def local_dataset_identity(root: Path, members: Iterable[str]) -> DatasetContentIdentity:
    dataset = root.resolve()
    normalized_members = tuple(sorted(set(members)))
    if not normalized_members:
        raise ValueError("dataset identity requires at least one selected task")
    task_digests = tuple((member, local_task_content_digest(dataset, member)) for member in normalized_members)
    payload = {
        "source": "local",
        "tasks": [{"name": member, "digest": digest} for member, digest in task_digests],
    }
    digest = _canonical_digest(payload)
    return DatasetContentIdentity("local", digest, normalized_members, f"sha256:{digest}", task_digests)


def registry_dataset_identity(dataset: str, *, client: RegistryMetadataClient | None = None) -> DatasetContentIdentity:
    registry = client or RegistryClientFactory.create()
    metadata = asyncio.run(registry.get_dataset_metadata(dataset))
    task_payloads = [_registry_task_payload(task) for task in metadata.task_ids]
    task_payloads.sort(key=lambda task: (str(task["name"]), json.dumps(task, sort_keys=True)))
    members = tuple(sorted(str(task["name"]) for task in task_payloads))
    if not members:
        raise ValueError("registry dataset identity requires at least one task")
    if not metadata.name or not metadata.version:
        raise ValueError("registry dataset must resolve to an immutable name and version")
    if len(set(members)) != len(members):
        raise ValueError("registry dataset contains duplicate task names")
    task_digests = tuple((str(task["name"]), _canonical_digest(task)) for task in task_payloads)
    payload = {
        "source": "registry",
        "name": metadata.name,
        "version": metadata.version,
        "dataset_content_hash": metadata.dataset_version_content_hash,
        "tasks": task_payloads,
        "files": sorted(
            ({"path": item.path, "content_hash": item.content_hash} for item in metadata.files),
            key=lambda item: item["path"],
        ),
    }
    return DatasetContentIdentity(
        "registry",
        _canonical_digest(payload),
        members,
        f"{metadata.name}@{metadata.version}",
        task_digests,
    )


def dataset_content_identity(
    dataset: str,
    *,
    base_dir: Path,
    client: RegistryMetadataClient | None = None,
) -> DatasetContentIdentity:
    candidate = Path(dataset).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    if candidate.is_dir():
        resolved = candidate.resolve()
        members = _local_task_names(resolved)
        if not members:
            raise ValueError(f"evaluator.dataset contains no Harbor task.toml directories: {resolved}")
        return local_dataset_identity(resolved, members)
    if client is None and os.environ.get("EVAL_STUB") == "1":
        return _stub_registry_dataset_identity(dataset)
    return registry_dataset_identity(dataset, client=client)


def _stub_registry_dataset_identity(dataset: str) -> DatasetContentIdentity:
    """Create deterministic offline task identities for the explicit stub evaluator."""
    name, separator, requested_version = dataset.partition("@")
    version = requested_version if separator else "stub-v1"
    tasks = [
        {
            "kind": "package",
            "name": f"task-{index}",
            "org": "evolve-stub",
            "package": f"task-{index}",
            "ref": f"sha256:{index:064x}",
        }
        for index in range(100)
    ]
    task_digests = tuple((str(task["name"]), _canonical_digest(task)) for task in tasks)
    payload = {"source": "registry", "name": name, "version": version, "tasks": tasks}
    return DatasetContentIdentity(
        "registry",
        _canonical_digest(payload),
        tuple(task for task, _digest in task_digests),
        f"{name}@{version}",
        task_digests,
    )


def selected_dataset_identity(manifest: Mapping[str, object], members: Iterable[str]) -> DatasetContentIdentity:
    identity = manifest.get("dataset_identity")
    task_digests = manifest.get("task_digests")
    normalized_members = tuple(sorted(set(members)))
    if (
        manifest.get("identity_status") != "verified"
        or not isinstance(identity, Mapping)
        or not isinstance(task_digests, Mapping)
        or not normalized_members
    ):
        raise ValueError("selected dataset identity requires a verified content manifest")
    source = identity.get("source")
    resolved_reference = identity.get("resolved_reference")
    if not isinstance(source, str) or not isinstance(resolved_reference, str):
        raise ValueError("selected dataset identity has invalid source metadata")
    selected_tasks: list[dict[str, str]] = []
    for member in normalized_members:
        digest = task_digests.get(member)
        if not isinstance(digest, str) or _SHA256_REF.fullmatch(f"sha256:{digest}") is None:
            raise ValueError(f"selected dataset identity is missing a content digest for {member!r}")
        selected_tasks.append({"name": member, "digest": digest})
    digest = _canonical_digest({"source": source, "tasks": selected_tasks})
    return DatasetContentIdentity(
        source,
        digest,
        normalized_members,
        resolved_reference,
        tuple((task["name"], task["digest"]) for task in selected_tasks),
    )


def _local_task_names(dataset: Path) -> tuple[str, ...]:
    if (dataset / "task.toml").is_file():
        return (dataset.name,)
    return tuple(sorted(path.name for path in dataset.iterdir() if path.is_dir() and (path / "task.toml").is_file()))


def local_task_content_digest(dataset: Path, member: str) -> str:
    relative_task = PurePosixPath(member)
    if relative_task.is_absolute() or len(relative_task.parts) != 1 or relative_task.parts[0] in {"", ".", ".."}:
        raise ValueError(f"invalid selected task name: {member!r}")
    task = dataset / member
    if not task.is_dir() or task.is_symlink():
        raise ValueError(f"selected task is not a regular directory: {member}")
    digest = hashlib.sha256()
    _update_digest(digest, "directory", ".", _mode_bytes(task))
    for path in sorted(task.rglob("*"), key=lambda item: item.relative_to(task).as_posix()):
        relative = path.relative_to(task).as_posix()
        if path.is_symlink():
            target = path.resolve()
            try:
                normalized_target = target.relative_to(task).as_posix()
            except ValueError as error:
                raise ValueError(f"symlink escapes selected task: {member}/{relative}") from error
            _update_digest(
                digest,
                "symlink",
                relative,
                _mode_bytes(path) + b"\0" + normalized_target.encode(),
            )
        elif path.is_file():
            _update_digest(
                digest,
                "file",
                relative,
                _mode_bytes(path) + b"\0" + path.read_bytes(),
            )
        elif path.is_dir():
            _update_digest(digest, "directory", relative, _mode_bytes(path))
        else:
            raise ValueError(f"unsupported dataset entry: {member}/{relative}")
    return digest.hexdigest()


def _registry_task_payload(task: object) -> dict[str, str]:
    if isinstance(task, GitTaskId) and task.git_commit_id and _GIT_COMMIT.fullmatch(task.git_commit_id):
        return {
            "kind": "git",
            "name": task.get_name(),
            "git_url": task.git_url,
            "git_commit_id": task.git_commit_id.lower(),
            "path": task.path.as_posix(),
        }
    if isinstance(task, PackageTaskId) and task.ref and _SHA256_REF.fullmatch(task.ref):
        return {
            "kind": "package",
            "name": task.get_name(),
            "org": task.org,
            "package": task.name,
            "ref": task.ref.lower(),
        }
    raise ValueError(f"registry dataset contains a task without an immutable task reference: {task!r}")


def _update_digest(digest: hashlib._Hash, kind: str, path: str, contents: bytes) -> None:
    for value in (kind.encode(), path.encode(), str(len(contents)).encode(), contents):
        digest.update(str(len(value)).encode())
        digest.update(b":")
        digest.update(value)
        digest.update(b"\0")


def _mode_bytes(path: Path) -> bytes:
    return f"{stat.S_IMODE(path.lstat().st_mode):04o}".encode()


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()
