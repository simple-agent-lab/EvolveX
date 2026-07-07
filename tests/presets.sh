#!/usr/bin/env bash
# M4 acceptance: four presets run and exhibit their loop characteristics.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

for NAME in autoresearch ahe hyperagents metaagent; do
  "$ROOT/bin/init-workspace.sh" "$TMP/$NAME" > /dev/null
  "$ROOT/bin/apply-preset.sh" "$TMP/$NAME" "$NAME" > /dev/null
  ( cd "$TMP/$NAME" \
    && HARNESS_STUB=1 EVOLVE_SEED=5 EVOLVE_MUTATE_VARIANT=fixed ./loop.sh 5 > /dev/null 2>&1 )
done

python3 - "$TMP" <<'PY'
import json, sys

base = sys.argv[1]

def load(name):
    nodes = [json.loads(l) for l in open(f"{base}/{name}/archive.jsonl") if l.strip()]
    gates = {}
    for n in nodes:
        try:
            gates[n["genid"]] = json.load(open(f"{base}/{name}/runs/gen-{n['genid']}/gate.json"))
        except FileNotFoundError:
            pass
    return nodes, gates

# autoresearch: greedy chain — every parent is the best valid node known so far
nodes, gates = load("autoresearch")
assert any(g.get("gate") == "hillclimb" for g in gates.values())
for n in nodes:
    if n["parent"] is None:
        continue
    prior_valid = [m for m in nodes if m["genid"] < n["genid"] and m["valid_parent"]]
    best = max(prior_valid, key=lambda m: (m["score"], m["genid"]))
    assert n["parent"] == best["genid"], \
        f"greedy violated: gen {n['genid']} picked {n['parent']}, best was {best['genid']}"
# hillclimb: valid only on strict improvement
for n in nodes:
    if n["parent"] is None:
        continue
    p = next(m for m in nodes if m["genid"] == n["parent"])
    assert n["valid_parent"] == (n["score"] > p["score"]), \
        f"hillclimb verdict wrong at gen {n['genid']}"
print(f"autoresearch OK: greedy hillclimb chain over {len(nodes)} gens")

# hyperagents: open gate — every clean gen is a valid parent
nodes, gates = load("hyperagents")
assert all(n["valid_parent"] for n in nodes), "open gate should keep every clean gen"
assert any(g.get("gate") == "open" for g in gates.values())
print(f"hyperagents OK: open population, {len(nodes)} gens all valid")

# metaagent: no gating at all
nodes, gates = load("metaagent")
assert all(n["status"] == "keep" and n["valid_parent"] for n in nodes)
assert any(g.get("gate") == "none" for g in gates.values())
print(f"metaagent OK: pure accumulation, {len(nodes)} gens")

# ahe: tournament + hillclimb ran
nodes, gates = load("ahe")
assert any(g.get("gate") == "hillclimb" for g in gates.values())
sel = json.load(open(f"{base}/ahe/runs/gen-{nodes[-1]['genid']}/select.json"))
assert sel["strategy"] == "tournament", sel
print(f"ahe OK: tournament selection under hillclimb gate, {len(nodes)} gens")
PY

echo "presets: PASS"
