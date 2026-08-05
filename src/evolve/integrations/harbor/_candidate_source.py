from __future__ import annotations

import os
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class UnsafeCandidateSourceError(ValueError):
    pass


@contextmanager
def candidate_source_archive(source: Path) -> Iterator[Path]:
    root = source.resolve()
    _validate_symlinks(root)
    with tempfile.TemporaryDirectory(prefix="evolve-miniswe-source-") as tempdir:
        archive_path = Path(tempdir) / "source.tar"
        with tarfile.open(archive_path, "w", dereference=False) as archive:
            archive.add(root, arcname=".", recursive=True, filter=_runtime_owned_member)
        archive_path.chmod(0o644)
        yield archive_path


def _validate_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_symlink():
            continue
        target = Path(os.readlink(path))
        if target.is_absolute():
            raise UnsafeCandidateSourceError(f"symlink escapes candidate source: {path.relative_to(root)}")
        try:
            resolved = (path.parent / target).resolve(strict=False)
            resolved.relative_to(root)
        except (RuntimeError, ValueError) as error:
            raise UnsafeCandidateSourceError(
                f"symlink escapes candidate source: {path.relative_to(root)}"
            ) from error


def _runtime_owned_member(member: tarfile.TarInfo) -> tarfile.TarInfo:
    member.uid = 0
    member.gid = 0
    member.uname = ""
    member.gname = ""
    member.mtime = 0
    if member.isdir() or member.mode & 0o111:
        member.mode = 0o700
    else:
        member.mode = 0o600
    return member
