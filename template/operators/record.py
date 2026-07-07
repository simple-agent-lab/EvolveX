#!/usr/bin/env python3
"""record — append one LedgerEntry (schema v2) to archive.jsonl.

INVARIANT #2 IN CODE: the frozen fields (score / score_ci / task_vector /
harness_version / audit) are copied verbatim from the frozen stamp
(runs/gen-<id>/stamp.json) and accepted from nowhere else. The protocol CLI
has no score flag — a forged --score dies at the argparse boundary
(EXIT_USAGE), and the contract tests assert that.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import (OperatorError, append_ledger, operator_main,  # noqa: E402
                                    read_json, ws_path)
from FROZEN.contracts.protocol import LedgerEntry  # noqa: E402


def mutated_paths(parent: int, gen: int) -> list:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"gen/{parent}", f"gen/{gen}"],
            cwd=ws_path(), capture_output=True, text=True, check=True,
        ).stdout
        return [l for l in out.splitlines() if l.strip()]
    except subprocess.CalledProcessError:
        return []


@operator_main("record")
def main(args):
    if not args.genesis and args.parent is None:
        raise OperatorError("--parent is required unless --genesis")

    run = ws_path("runs", f"gen-{args.gen}")
    stamp = read_json(run / "stamp.json")
    if stamp is None:
        raise OperatorError("refusing to write a ledger line without a frozen stamp")
    mutate_info = read_json(run / "mutate.json", {})
    gate_info = read_json(run / "gate.json", {"status": "keep", "valid_parent": True})
    novelty_info = read_json(run / "novelty.json", {})

    mutated = [] if args.genesis else mutated_paths(args.parent, args.gen)
    op_diff = sorted({p for p in mutated if p.startswith("operators/")})

    entry = LedgerEntry(
        genid=args.gen,
        parent=None if args.genesis else args.parent,
        tag=f"gen/{args.gen}",
        # frozen-stamped fields — from stamp.json only
        score=stamp["score"],
        score_ci=stamp["score_ci"],
        task_vector=stamp["task_vector"],
        harness_version=stamp["harness_version"],
        audit=stamp["audit"],
        # lineage & cost
        cost=mutate_info.get("cost", {"tokens": 0, "eval_minutes": 0}),
        mutated=mutated,
        operator_diff=op_diff[0] if op_diff else None,
        operator_reverted=False,
        # weights-gen fields (filled from M6)
        weights_ref=None,
        train=None,
        # evolvable judgement & memory
        status=gate_info.get("status", "keep"),
        valid_parent=bool(gate_info.get("valid_parent", True)),
        used_insights=mutate_info.get("used_insights", []),
        predicted_fixes=mutate_info.get("predicted_fixes", []),
        verified_fixes=[],  # reflect fills this loop (M2)
        novelty=novelty_info.get("novelty"),
        note=args.note if args.note is not None else mutate_info.get("note", ""),
    )

    from FROZEN.contracts.protocol import payload, validate
    data = payload(entry)
    errs = validate(data, LedgerEntry)
    if errs:
        raise OperatorError(f"entry violates ledger schema v2: {errs}")
    append_ledger(data)
    return entry


if __name__ == "__main__":
    main()
