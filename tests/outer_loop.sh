#!/usr/bin/env bash
# M7-mechanics acceptance: the outer loop arms on a plateau, stages stamped
# training data, and stops cleanly at the (infra-blocked) engine boundary.
# Plus: the audit anomaly path quarantines suspicious jumps.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "== outer loop: plateau -> distill -> decontam -> engine dispatch"
"$ROOT/bin/init-workspace.sh" "$TMP/ws" > /dev/null
( cd "$TMP/ws" \
  && HARNESS_STUB=1 EVOLVE_SEED=9 EVOLVE_TRAIN_PLATEAU=2 ./loop.sh 8 2>&1 \
    | grep -E "outer loop" | sed 's/^/  /' )
python3 - "$TMP/ws" <<'PY'
import json, sys
from pathlib import Path
ws = Path(sys.argv[1])
reqs = sorted(ws.glob("runs/train-requests/req-*.json"))
assert reqs, "no train request was ever filed despite a plateau"
req = json.loads(reqs[0].read_text())
assert req["stamped"] is True, req
assert req["engine"] == "not-wired", req
stamp = json.loads((ws / (req["manifest"] + ".stamp.json")).read_text())
assert stamp["decontam_stamp"] == "frozen-ok" and stamp["samples"] > 0
print(f"  outer loop OK: {len(reqs)} request(s); first staged {stamp['samples']} "
      f"stamped samples and stopped at the engine boundary")
PY

echo "== audit anomaly path: suspicious jumps get quarantined"
"$ROOT/bin/init-workspace.sh" "$TMP/wsa" > /dev/null
( cd "$TMP/wsa" \
  && HARNESS_STUB=1 EVOLVE_SEED=9 EVOLVE_AUDIT_JUMP=0.05 ./loop.sh 8 > /dev/null 2>&1 )
python3 - "$TMP/wsa" <<'PY'
import json, sys
from pathlib import Path
ws = Path(sys.argv[1])
nodes = [json.loads(l) for l in (ws / "archive.jsonl").read_text().splitlines() if l.strip()]
pending = [n for n in nodes if n["audit"] == "pending"]
assert pending, "no gen was ever quarantined despite a 0.05 jump threshold"
best = json.loads((ws / "best_ever.json").read_text())
for n in pending:
    assert n["valid_parent"] is False, "a pending-audit gen stayed a valid parent"
    assert best["genid"] != n["genid"], "a pending-audit gen became champion"
print(f"  audit OK: {len(pending)} gen(s) quarantined — not champion, not parents, "
      f"and decontam excludes them from training")
PY

echo "== lineage report runs"
python3 "$ROOT/bin/lineage-report.py" "$TMP/ws" | head -8 | sed 's/^/  /'

echo
echo "outer_loop: PASS"
