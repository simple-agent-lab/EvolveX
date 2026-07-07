#!/usr/bin/env bash
# FROZEN — stamps canonical fields from eval output into runs/gen-<id>/stamp.json
# (invariant #2: score enters the ledger only via this stamp, agents never pass it)
# and maintains best_ever.json (invariant #3: recomputed from true score by a fixed
# rule; changing champion requires a replication re-eval — both runs must beat it).
set -euo pipefail
GEN="${1:?usage: stamp.sh <genid>}"
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$WS" "$GEN" <<'PY'
import json, os, subprocess, sys

ws, gen = sys.argv[1], sys.argv[2]
out = os.path.join(ws, "runs", f"gen-{gen}")
res = json.load(open(os.path.join(out, "result.json")))

stamp = {
    "genid": int(gen),
    "score": res["score"],
    "score_ci": res["score_ci"],
    "task_vector": res["task_vector"],
    "harness_version": res["harness_version"],
    "audit": "clean",  # audit.sh escalates this on anomaly (wired at M3+)
}
with open(os.path.join(out, "stamp.json"), "w") as f:
    json.dump(stamp, f, indent=1)

best_path = os.path.join(ws, "best_ever.json")
best = json.load(open(best_path)) if os.path.exists(best_path) else None
if best is None or stamp["score"] > best["score"]:
    # replication: re-run canonical eval once; both runs must beat the incumbent
    subprocess.run([os.path.join(ws, "FROZEN", "eval.sh"), gen],
                   check=True, stdout=subprocess.DEVNULL)
    res2 = json.load(open(os.path.join(out, "result.json")))
    if best is None or res2["score"] > best["score"]:
        with open(best_path, "w") as f:
            json.dump({"genid": int(gen), "score": res2["score"],
                       "harness_version": res2["harness_version"]}, f, indent=1)
PY

echo "$WS/runs/gen-$GEN/stamp.json"
