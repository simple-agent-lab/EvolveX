"""Materialize or verify the shared, content-pinned Terminal-Bench 2.0 subset."""

from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path

from evolve.splits import task_content_digests

MANIFEST_PATH = Path(__file__).with_name("dataset-manifest.json")


def _source_root(path: Path) -> Path:
    nested = path / "terminal-bench"
    return nested if nested.is_dir() else path


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text())


def _expected_tasks(manifest: dict[str, object]) -> dict[str, str]:
    tasks = manifest.get("tasks")
    if not isinstance(tasks, dict):
        raise SystemExit("dataset manifest has no task mapping")
    normalized = {str(name): str(digest).removeprefix("sha256:") for name, digest in tasks.items()}
    if any(len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest) for digest in normalized.values()):
        raise SystemExit("dataset manifest contains an invalid sha256 digest")
    return normalized


def _mismatch_details(expected: dict[str, str], observed: dict[str, str], *, allow_extra: bool = False) -> str:
    missing = sorted(set(expected) - set(observed))
    extra = sorted(set(observed) - set(expected))
    mismatched = sorted(name for name in expected.keys() & observed.keys() if observed[name] != expected[name])
    details: list[str] = []
    if missing:
        details.append("missing=" + ",".join(missing))
    if extra and not allow_extra:
        details.append("extra=" + ",".join(extra))
    if mismatched:
        details.append("digest_mismatch=" + ",".join(mismatched))
    return "; ".join(details)


def _verify(root: Path, expected: dict[str, str], *, allow_extra: bool = False) -> str:
    return _mismatch_details(expected, task_content_digests(root), allow_extra=allow_extra)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="exported terminal-bench@2.0 task directory")
    parser.add_argument("destination", type=Path, help="pinned subset directory")
    args = parser.parse_args(argv)

    source = _source_root(args.source.expanduser().resolve())
    destination = args.destination.expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"source dataset does not exist: {source}")

    manifest = _manifest()
    expected = _expected_tasks(manifest)
    source_mismatch = _verify(source, expected, allow_extra=True)
    if source_mismatch:
        raise SystemExit("source does not match the pinned subset: " + source_mismatch)

    if destination.exists():
        destination_mismatch = _verify(destination, expected)
        if destination_mismatch:
            raise SystemExit("existing destination does not match the pinned subset: " + destination_mismatch)
        print(f"Reused verified dataset at {destination}")
        return 0

    pending = destination.with_name(f".{destination.name}.pending-{uuid.uuid4().hex}")
    pending.mkdir(parents=True)
    try:
        for name in sorted(expected):
            shutil.copytree(source / name, pending / name)
        copied_mismatch = _verify(pending, expected)
        if copied_mismatch:
            raise RuntimeError("copied dataset does not match the pinned subset: " + copied_mismatch)
        (pending / "dataset-source.json").write_text(
            json.dumps(
                {
                    "dataset": manifest["dataset"],
                    "manifest": manifest["name"],
                    "selection": manifest["selection"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        pending.replace(destination)
    except BaseException:
        shutil.rmtree(pending, ignore_errors=True)
        raise

    print(f"Materialized {len(expected)} tasks at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
