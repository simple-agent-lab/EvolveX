#!/usr/bin/env python3
"""FROZEN — stamp canonical fields from eval output into runs/gen-<id>/stamp.json
(invariant #2: scores enter the ledger only via this stamp) and maintain
best_ever.json (invariant #3: fixed rule over true scores; changing champion
requires a replication re-eval — both runs must beat the incumbent).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS))

from FROZEN.contracts.protocol import Stamp, payload, validate  # noqa: E402


def main() -> None:
    gen = sys.argv[1]
    out = WS / "runs" / f"gen-{gen}"
    res = json.loads((out / "result.json").read_text())

    best_path = WS / "best_ever.json"
    best = json.loads(best_path.read_text()) if best_path.exists() else None

    # anomaly escalation: a jump past the champion by more than
    # EVOLVE_AUDIT_JUMP marks the gen audit=pending — it cannot become
    # champion (below), cannot be a valid parent (open gate requires clean),
    # and cannot train (decontam requires clean) until a human/auditor clears
    # it. Off by default; audit.sh lists pending gens.
    audit = "clean"
    jump = os.environ.get("EVOLVE_AUDIT_JUMP")
    if jump and best is not None and res["score"] > best["score"] + float(jump):
        audit = "pending"
        print(f"stamp: score {res['score']} jumped past champion {best['score']} "
              f"by > {jump} — audit=pending", file=sys.stderr)

    stamp = Stamp(
        genid=int(gen),
        score=res["score"],
        score_ci=res["score_ci"],
        task_vector=res["task_vector"],
        harness_version=res["harness_version"],
        audit=audit,
    )
    data = payload(stamp)
    errs = validate(data, Stamp)
    if errs:
        print(f"stamp: eval output violates the Harness contract: {errs}", file=sys.stderr)
        sys.exit(1)
    (out / "stamp.json").write_text(json.dumps(data, indent=1) + "\n")

    if audit == "clean" and (best is None or data["score"] > best["score"]):
        # replication: re-run canonical eval once; both runs must beat the incumbent
        subprocess.run([str(WS / "FROZEN" / "eval.sh"), gen],
                       check=True, stdout=subprocess.DEVNULL)
        res2 = json.loads((out / "result.json").read_text())
        if best is None or res2["score"] > best["score"]:
            best_path.write_text(json.dumps(
                {"genid": int(gen), "score": res2["score"],
                 "harness_version": res2["harness_version"]}, indent=1) + "\n")

    print(str(out / "stamp.json"))


if __name__ == "__main__":
    main()
