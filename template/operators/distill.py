#!/usr/bin/env python3
"""distill — trajectories -> training data (outer loop T2, design §03).

Task-level selection over the dev-lane trajectories in runs/*/dev/trajs/:
  - SFT set  : successful trajectories (a task succeeding qualifies its
               trajectory even in a low-scoring gen — failed gens still
               contain good task runs)
  - DPO pairs: same task, success vs failure from different gens
  - dedup    : by trajectory hash, with a per-task cap (EVOLVE_DISTILL_CAP,
               default 3) so the data distribution doesn't collapse onto
               easy tasks
Every manifest sample traces to (genid, task_id, trajectory_hash, path).

This operator is EVOLVABLE (selection strategy, mixes, curricula). The
non-negotiables — dev-split-only, audit-clean sources — are re-enforced by
FROZEN/decontam.py, which this operator cannot reach; train engines reject
unstamped manifests (invariant #4).
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import operator_main, read_archive, ws_path  # noqa: E402
from FROZEN.contracts.protocol import DistillOutput  # noqa: E402


@operator_main("distill")
def main(args):
    audit = {n["genid"]: n.get("audit") for n in read_archive()}
    cap = int(os.environ.get("EVOLVE_DISTILL_CAP", "3"))

    by_task = {}  # task_id -> {"passed": [...], "failed": [...]}
    seen_hashes = set()
    latest_gen = -1
    for traj_path in sorted(ws_path("runs").glob("gen-*/dev/trajs/task_*.json")):
        m = re.match(r"gen-(\d+)$", traj_path.parents[2].name)
        if not m:
            continue
        gen = int(m.group(1))
        if audit.get(gen) not in (None, "clean"):
            continue  # exploit-flagged gens never train (decontam re-enforces)
        traj = json.loads(traj_path.read_text())
        if traj["trajectory_hash"] in seen_hashes:
            continue
        seen_hashes.add(traj["trajectory_hash"])
        latest_gen = max(latest_gen, gen)
        bucket = by_task.setdefault(traj["task_id"], {"passed": [], "failed": []})
        bucket["passed" if traj["passed"] else "failed"].append(
            {"genid": gen, "trajectory_hash": traj["trajectory_hash"],
             "path": str(traj_path.relative_to(ws_path()))})

    lines, sft, dpo = [], 0, 0
    for task_id, bucket in sorted(by_task.items()):
        for sample in bucket["passed"][:cap]:
            lines.append({"kind": "sft", "task_id": task_id, **sample})
            sft += 1
        for chosen, rejected in list(zip(bucket["passed"], bucket["failed"]))[:cap]:
            lines.append({"kind": "dpo", "task_id": task_id,
                          "chosen": chosen, "rejected": rejected})
            dpo += 1

    name = f"distill-gen{latest_gen}.jsonl" if latest_gen >= 0 else "distill-empty.jsonl"
    manifest = ws_path("manifests", name)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lines)
    manifest.write_text(body)

    return DistillOutput(
        ok=True, manifest=str(manifest.relative_to(ws_path())), sft=sft, dpo=dpo,
        extras={"tasks": len(by_task), "cap": cap,
                "manifest_sha256": hashlib.sha256(body.encode()).hexdigest()})


if __name__ == "__main__":
    main()
