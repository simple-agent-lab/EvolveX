"""Materialize the pinned Terminal-Bench subset used by the AHE Codex recipe."""

from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path

from evolve.splits import task_content_digests


def _source_root(path: Path) -> Path:
    nested = path / "terminal-bench"
    return nested if nested.is_dir() else path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="exported terminal-bench@2.0 task directory")
    parser.add_argument("destination", type=Path, help="new subset directory")
    args = parser.parse_args()

    source = _source_root(args.source.expanduser().resolve())
    destination = args.destination.expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"source dataset does not exist: {source}")
    if destination.exists():
        raise SystemExit(f"destination already exists: {destination}")

    manifest = json.loads((Path(__file__).with_name("dataset-manifest.json")).read_text())
    expected = {str(name): str(digest) for name, digest in manifest["tasks"].items()}
    observed = task_content_digests(source)
    missing = sorted(set(expected) - set(observed))
    mismatched = sorted(name for name, digest in expected.items() if observed.get(name) != digest)
    if missing or mismatched:
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if mismatched:
            details.append("digest_mismatch=" + ",".join(mismatched))
        raise SystemExit("source does not match the pinned subset: " + "; ".join(details))

    pending = destination.with_name(f".{destination.name}.pending-{uuid.uuid4().hex}")
    pending.mkdir(parents=True)
    try:
        for name in sorted(expected):
            shutil.copytree(source / name, pending / name)
        copied = task_content_digests(pending)
        if copied != expected:
            raise RuntimeError("copied dataset does not match pinned task digests")
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
