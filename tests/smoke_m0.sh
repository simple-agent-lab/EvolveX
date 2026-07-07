#!/usr/bin/env bash
# M0 acceptance (design v0.4 §11):
#   idle-run 5 generations on the stub harness; the ledger grows a lineage;
#   `git reset` does not erase history; contracts hold on the fresh workspace.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "== init workspace"
"$ROOT/bin/init-workspace.sh" "$TMP/ws"
cd "$TMP/ws"

echo "== run 5 generations (stub harness)"
HARNESS_STUB=1 EVOLVE_SEED=42 ./loop.sh 5

echo "== ledger checks"
python3 - <<'PY'
import json

nodes = [json.loads(l) for l in open("archive.jsonl") if l.strip()]
assert len(nodes) == 6, f"expected 6 ledger entries (gen0 + 5), got {len(nodes)}"
ids = {n["genid"] for n in nodes}
assert ids == set(range(6)), f"genids not contiguous: {sorted(ids)}"

REQUIRED = ["genid", "parent", "tag", "score", "score_ci", "task_vector",
            "harness_version", "audit", "cost", "mutated", "operator_diff",
            "operator_reverted", "weights_ref", "train", "status", "valid_parent",
            "used_insights", "predicted_fixes", "verified_fixes", "novelty", "note"]
for n in nodes:
    missing = [k for k in REQUIRED if k not in n]
    assert not missing, f"gen {n['genid']} missing schema-v2 keys: {missing}"
    if n["genid"] == 0:
        assert n["parent"] is None, "genesis must have parent=null"
    else:
        assert n["parent"] in ids and n["parent"] < n["genid"], \
            f"gen {n['genid']} has bad parent {n['parent']}"
        assert n["mutated"], f"gen {n['genid']} recorded no mutated paths"
    assert 0.0 <= n["score"] <= 1.0
    assert len(n["task_vector"]) == 20
    assert n["audit"] == "clean"

parents = {n["parent"] for n in nodes if n["parent"] is not None}
print(f"ledger OK: lineage over parents {sorted(parents)}")
PY

echo "== git tags gen/0..gen/5 exist"
for i in 0 1 2 3 4 5; do
  git rev-parse -q --verify "refs/tags/gen/$i" > /dev/null \
    || { echo "missing tag gen/$i" >&2; exit 1; }
done

echo "== best_ever.json exists and matches the ledger max"
python3 - <<'PY'
import json
best = json.load(open("best_ever.json"))
nodes = [json.loads(l) for l in open("archive.jsonl") if l.strip()]
assert best["score"] == max(n["score"] for n in nodes), (best, max(n["score"] for n in nodes))
print(f"best-ever OK: gen {best['genid']} @ {best['score']}")
PY

echo "== git reset --hard gen/0 must not erase untracked history"
git reset --hard -q gen/0
test "$(wc -l < archive.jsonl | tr -d ' ')" -eq 6 || { echo "ledger lost after reset" >&2; exit 1; }
test -f best_ever.json || { echo "best_ever lost after reset" >&2; exit 1; }

echo "== contracts on the workspace"
python3 FROZEN/contracts/run_contracts.py

echo
echo "M0 smoke: PASS"
