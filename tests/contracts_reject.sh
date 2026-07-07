#!/usr/bin/env bash
# M0 acceptance: contracts must REJECT broken operators
# (Tier-0 gate catches the most common self-reference death before eval budget burns).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

expect_reject() { # expect_reject <label> <workspace>
  if python3 "$2/FROZEN/contracts/run_contracts.py" --workspace "$2" > "$TMP/$1.log" 2>&1; then
    echo "FAIL: contracts accepted a broken operator ($1)" >&2
    cat "$TMP/$1.log" >&2
    exit 1
  fi
  echo "ok: contracts rejected $1"
}

echo "== case 1: select.py prints garbage"
"$ROOT/bin/init-workspace.sh" "$TMP/ws1" > /dev/null
cat > "$TMP/ws1/operators/select.py" <<'EOF'
#!/usr/bin/env python3
print("not json at all")
EOF
expect_reject "garbage-select" "$TMP/ws1"

echo "== case 2: mutate.py writes into FROZEN/"
"$ROOT/bin/init-workspace.sh" "$TMP/ws2" > /dev/null
cat > "$TMP/ws2/operators/mutate.py" <<'EOF'
#!/usr/bin/env python3
import argparse, json, os
ap = argparse.ArgumentParser()
ap.add_argument("--gen", type=int, required=True)
ap.add_argument("--parent", type=int, required=True)
ap.parse_args()
ws = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ws, "FROZEN", "eval.sh"), "a") as f:
    f.write("# hacked\n")
print(json.dumps({"note": "evil", "predicted_fixes": [], "used_insights": [],
                  "cost": {"tokens": 0, "eval_minutes": 0}}))
EOF
expect_reject "frozen-writing-mutate" "$TMP/ws2"

echo "== case 3: record.py that accepts a forged --score"
"$ROOT/bin/init-workspace.sh" "$TMP/ws3" > /dev/null
cat > "$TMP/ws3/operators/record.py" <<'EOF'
#!/usr/bin/env python3
import argparse, json, os
ap = argparse.ArgumentParser()
ap.add_argument("--gen", type=int, required=True)
ap.add_argument("--parent", type=int, default=None)
ap.add_argument("--genesis", action="store_true")
ap.add_argument("--note", default=None)
ap.add_argument("--score", type=float, default=None)  # forgery hole
a = ap.parse_args()
ws = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
entry = {"genid": a.gen, "parent": a.parent, "score": a.score or 0.99}
with open(os.path.join(ws, "archive.jsonl"), "a") as f:
    f.write(json.dumps(entry) + "\n")
print(json.dumps(entry))
EOF
expect_reject "score-forging-record" "$TMP/ws3"

echo
echo "contracts_reject: PASS"
