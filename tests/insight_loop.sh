#!/usr/bin/env bash
# M2 acceptance: the insight loop closes end to end —
#   falsification settles predictions -> playbook grows evidence-backed entries
#   -> mutate consumes them (used_insights) -> reflect backfills support/refute.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$ROOT/bin/init-workspace.sh" "$TMP/ws" > /dev/null
cd "$TMP/ws"
HARNESS_STUB=1 EVOLVE_SEED=7 ./loop.sh 10 > /dev/null 2>&1

python3 - <<'PY'
import json

nodes = [json.loads(l) for l in open("archive.jsonl") if l.strip()]
assert len(nodes) >= 8, f"expected >=8 ledger entries, got {len(nodes)}"

# falsification closed: some parent prediction got settled (verified or refuted)
settled = [n for n in nodes if n.get("verified_fixes") or n.get("refuted_fixes")]
assert settled, "no predictions were ever settled — falsification closure is dead"

# playbook grew evidence-backed entries via delta ops
ops = [json.loads(l) for l in open("insights/playbook.jsonl") if l.strip()]
assert ops, "playbook is empty after 10 gens with settled predictions"
for op in ops:
    assert op["op"] in ("ADD", "UPDATE", "RETIRE"), op
    assert op["evidence"], f"entry {op['id']} has no evidence genids"

# fold by id (last line wins) -> current state
state = {}
for op in ops:
    state[op["id"]] = op
assert any(e["status"] == "active" for e in state.values())

# consumption: some later gen retrieved insights during mutation
consumers = [n for n in nodes if n.get("used_insights")]
assert consumers, "no gen ever consumed a playbook insight — retrieval is dead"

# credit backfill: consumed insights accumulated support or refute
credited = [e for e in state.values() if e["support"] + e["refute"] > 1]
assert credited, "no insight ever accumulated credit beyond its birth"

print(f"insight loop OK: {len(settled)} gens settled predictions, "
      f"{len(state)} playbook entries, {len(consumers)} consumer gens, "
      f"{len(credited)} credited entries")
PY

echo "insight_loop: PASS"
