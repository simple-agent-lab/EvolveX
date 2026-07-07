#!/usr/bin/env bash
# FROZEN — trace-audit surface (load-bearing on the weights path).
#
# Mechanical escalation is live: FROZEN/stamp.py marks audit=pending when a
# score jumps past the champion by more than EVOLVE_AUDIT_JUMP. Pending gens
# cannot become champion, cannot be valid parents (gates require clean), and
# cannot train (decontam requires clean).
#
# This tool lists what awaits review. Clearing/flagging a pending gen is a
# human/LLM-auditor act performed OUTSIDE the loop (read the gen's diff +
# runs/gen-<id>/ trajectories, judge real-capability vs exploit); the
# LLM-auditor lands with real trajectories (post-M1 infra).
set -euo pipefail
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "gens awaiting audit (audit=pending):"
python3 - "$WS" <<'PY'
import json, sys
from pathlib import Path
ws = Path(sys.argv[1])
found = False
for stamp_path in sorted(ws.glob("runs/gen-*/stamp.json")):
    stamp = json.loads(stamp_path.read_text())
    if stamp.get("audit") == "pending":
        found = True
        print(f"  gen {stamp['genid']}: score={stamp['score']} "
              f"-> review diff: git show gen/{stamp['genid']}; "
              f"trajectories: {stamp_path.parent}/dev/")
if not found:
    print("  (none)")
PY
