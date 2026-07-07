#!/usr/bin/env python3
"""FROZEN — training-data decontamination + stamping (invariant #4).

The one attack surface auto-train opens on the frozen gate: if gate/sealed
task trajectories ever enter training data, canonical scores become memory
tests and invariants 1–3 are hollowed out. This gate enforces, per sample:

  1. task_id ∈ splits.json["dev"]        (gate/sealed tasks NEVER train)
  2. source gen's ledger audit == clean  (exploit trajectories never train —
                                          a hack trained into weights is
                                          unreadable and compounds)

On pass, writes a tamper-evident sidecar stamp binding the manifest's sha256.
Train engines reject manifests without a matching stamp. distill.py is
evolvable; this file is not reachable from it.

Usage:
  decontam.py stamp  <manifest.jsonl>   -> writes <manifest>.stamp.json, exit 0
  decontam.py verify <manifest.jsonl>   -> exit 0 iff stamp exists and matches
"""
import hashlib
import json
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp_path(manifest: Path) -> Path:
    return manifest.with_suffix(manifest.suffix + ".stamp.json")


def sources(line: dict):
    if line["kind"] == "dpo":
        yield line["chosen"]
        yield line["rejected"]
    else:
        yield line


def cmd_stamp(manifest: Path) -> int:
    splits = json.loads((WS / "FROZEN" / "splits.json").read_text())
    dev = set(splits["dev"])
    audit = {}
    arc = WS / "archive.jsonl"
    if arc.exists():
        for l in arc.read_text().splitlines():
            if l.strip():
                n = json.loads(l)
                audit[n["genid"]] = n.get("audit")

    lines = [json.loads(l) for l in manifest.read_text().splitlines() if l.strip()]
    for i, line in enumerate(lines):
        if line["task_id"] not in dev:
            print(f"decontam: REJECT — sample {i} task {line['task_id']} is outside the "
                  f"dev split (gate/sealed tasks never train)", file=sys.stderr)
            return 1
        for src in sources(line):
            if audit.get(src["genid"]) != "clean":
                print(f"decontam: REJECT — sample {i} sources gen {src['genid']} whose "
                      f"audit is {audit.get(src['genid'])!r}, not clean", file=sys.stderr)
                return 1
            traj = WS / src["path"]
            if not traj.exists():
                print(f"decontam: REJECT — sample {i} trajectory missing: {src['path']}",
                      file=sys.stderr)
                return 1
            if json.loads(traj.read_text())["trajectory_hash"] != src["trajectory_hash"]:
                print(f"decontam: REJECT — sample {i} trajectory hash mismatch "
                      f"({src['path']})", file=sys.stderr)
                return 1

    stamp = {"decontam_stamp": "frozen-ok",
             "manifest_sha256": sha256(manifest),
             "samples": len(lines),
             "protocol": "dev-split-only + audit-clean + trajectory-hash"}
    stamp_path(manifest).write_text(json.dumps(stamp, indent=1) + "\n")
    print(f"decontam: stamped {manifest.name} ({len(lines)} samples)")
    return 0


def cmd_verify(manifest: Path) -> int:
    sp = stamp_path(manifest)
    if not sp.exists():
        print(f"decontam: no stamp for {manifest.name} — train engines must reject",
              file=sys.stderr)
        return 1
    stamp = json.loads(sp.read_text())
    if stamp.get("manifest_sha256") != sha256(manifest):
        print(f"decontam: STAMP MISMATCH — {manifest.name} changed after stamping",
              file=sys.stderr)
        return 1
    print(f"decontam: stamp verified ({stamp['samples']} samples)")
    return 0


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("stamp", "verify"):
        print(__doc__, file=sys.stderr)
        return 2
    manifest = Path(sys.argv[2])
    if not manifest.is_absolute():
        manifest = WS / manifest
    if not manifest.exists():
        print(f"decontam: manifest not found: {manifest}", file=sys.stderr)
        return 1
    return cmd_stamp(manifest) if sys.argv[1] == "stamp" else cmd_verify(manifest)


if __name__ == "__main__":
    sys.exit(main())
