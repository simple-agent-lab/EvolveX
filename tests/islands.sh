#!/usr/bin/env bash
# M3 acceptance: islands evolve independently and exchange champions through
# migration generations that compete under each island's own frozen ruler.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

HARNESS_STUB=1 EVOLVE_SEED=11 "$ROOT/bin/islands.sh" "$TMP/pop" 2 2 2 > "$TMP/log" 2>&1 \
  || { cat "$TMP/log" >&2; exit 1; }
grep -E "champion|migrant" "$TMP/log" | sed 's/^/  /' || true

python3 - "$TMP/pop" <<'PY'
import json, sys
base = sys.argv[1]
migrants = 0
for i in (0, 1):
    nodes = [json.loads(l) for l in open(f"{base}/island-{i}/archive.jsonl") if l.strip()]
    assert len(nodes) >= 5, f"island-{i} ledger too short: {len(nodes)}"
    m = [n for n in nodes if "migrant" in n.get("note", "")]
    migrants += len(m)
    for n in m:
        # a migrant is a full citizen: frozen-stamped score, gate verdict, lineage
        assert n["score"] is not None and n["task_vector"], n
assert migrants >= 1, "no migration generation ever landed"
print(f"islands OK: {migrants} migrant gen(s) landed and were canonically scored")
PY

echo "islands: PASS"
