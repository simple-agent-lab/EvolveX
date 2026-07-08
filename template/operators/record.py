#!/usr/bin/env python3
"""record — append one LedgerEntry (schema v2) to archive.jsonl.

INVARIANT #2 IN CODE: the frozen fields (score / score_ci / task_vector /
harness_version / audit) are copied verbatim from the frozen stamp
(runs/gen-<id>/stamp.json) and accepted from nowhere else. The protocol CLI
has no score flag — a forged --score dies at the argparse boundary
(EXIT_USAGE), and the contract tests assert that.
"""
import subprocess

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


def falsify(parent: int, gen: int) -> tuple:
    """AHE-style falsification closure: the PARENT's predicted_fixes are
    verified against THIS gen's dev results — this gen's rollout measured the
    parent's committed tree, i.e. exactly the state the parent's mutation
    produced. Pure bookkeeping (no judgement), so it lives here; reflect.py
    turns the outcome into insights."""
    from FROZEN.contracts.oplib import read_archive
    parent_entry = next((n for n in read_archive() if n["genid"] == parent), None)
    if not parent_entry or not parent_entry.get("predicted_fixes"):
        return [], []
    fb = read_json(ws_path("runs", f"gen-{gen}", "dev", "feedback.json"), {})
    passed = {f"task_{t}" for t, b in zip(fb.get("task_ids", []), fb.get("task_vector", ""))
              if b == "1"}
    preds = parent_entry["predicted_fixes"]
    verified = [p for p in preds if p in passed]
    refuted = [p for p in preds if p not in passed]
    return verified, refuted


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
    verified, refuted = ([], []) if args.genesis else falsify(args.parent, args.gen)
    admission = read_json(run / "admission.json", {})

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
        operator_reverted=bool(admission.get("reverted", False)),
        # weights-gen fields (filled from M6)
        weights_ref=None,
        train=None,
        # evolvable judgement & memory
        status=gate_info.get("status", "keep"),
        valid_parent=bool(gate_info.get("valid_parent", True)),
        used_insights=mutate_info.get("used_insights", []),
        predicted_fixes=mutate_info.get("predicted_fixes", []),
        # verified_fixes on gen N settles the PARENT's predictions (see falsify)
        verified_fixes=verified,
        novelty=novelty_info.get("novelty"),
        note=args.note if args.note is not None else mutate_info.get("note", ""),
        extras={"refuted_fixes": refuted},
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
