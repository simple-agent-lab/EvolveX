#!/usr/bin/env python3
"""record — append one ledger schema-v2 line to archive.jsonl.

INVARIANT #2 IN CODE: the frozen fields (score / score_ci / task_vector /
harness_version / audit) are read ONLY from the frozen stamp
(runs/gen-<id>/stamp.json). This operator deliberately accepts no score
argument — argparse will exit(2) on any attempt, and the contract tests
assert that forging fails.

Contract: appends a JSON line with every schema-v2 key present (nulls where a
later milestone fills them), prints the appended line.
"""
import argparse
import json
import os
import subprocess
import sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path: str, default=None):
    return json.load(open(path)) if os.path.exists(path) else default


def mutated_paths(parent: int, gen: int) -> list:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"gen/{parent}", f"gen/{gen}"],
            cwd=WS, capture_output=True, text=True, check=True,
        ).stdout
        return [l for l in out.splitlines() if l.strip()]
    except subprocess.CalledProcessError:
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", type=int, required=True)
    ap.add_argument("--parent", type=int, default=None)
    ap.add_argument("--genesis", action="store_true")
    ap.add_argument("--note", default=None)
    a = ap.parse_args()
    if not a.genesis and a.parent is None:
        ap.error("--parent is required unless --genesis")

    run_dir = os.path.join(WS, "runs", f"gen-{a.gen}")
    stamp = load(os.path.join(run_dir, "stamp.json"))
    if stamp is None:
        print("record: refusing to write a ledger line without a frozen stamp", file=sys.stderr)
        sys.exit(1)
    mutate_info = load(os.path.join(run_dir, "mutate.json"), {})
    gate_info = load(os.path.join(run_dir, "gate.json"), {"status": "keep", "valid_parent": True})
    novelty_info = load(os.path.join(run_dir, "novelty.json"), {})

    mutated = [] if a.genesis else mutated_paths(a.parent, a.gen)
    op_diff = sorted({p for p in mutated if p.startswith("operators/")})

    entry = {
        "genid": a.gen,
        "parent": None if a.genesis else a.parent,
        "tag": f"gen/{a.gen}",
        # —— frozen-stamped fields (copied from stamp.json, never from args) ——
        "score": stamp["score"],
        "score_ci": stamp["score_ci"],
        "task_vector": stamp["task_vector"],
        "harness_version": stamp["harness_version"],
        "audit": stamp["audit"],
        # —— lineage & cost ——
        "cost": mutate_info.get("cost", {"tokens": 0, "eval_minutes": 0}),
        "mutated": mutated,
        "operator_diff": op_diff[0] if op_diff else None,
        "operator_reverted": False,
        # —— weights-gen fields (filled from M6) ——
        "weights_ref": None,
        "train": None,
        # —— evolvable judgement & memory ——
        "status": gate_info.get("status", "keep"),
        "valid_parent": bool(gate_info.get("valid_parent", True)),
        "used_insights": mutate_info.get("used_insights", []),
        "predicted_fixes": mutate_info.get("predicted_fixes", []),
        "verified_fixes": [],  # reflect.py fills this loop (M2)
        "novelty": novelty_info.get("novelty"),
        "note": a.note if a.note is not None else mutate_info.get("note", ""),
    }

    with open(os.path.join(WS, "archive.jsonl"), "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
