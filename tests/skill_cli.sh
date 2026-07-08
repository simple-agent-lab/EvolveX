#!/usr/bin/env bash
# Skill-surface acceptance: an agent operates the workspace end to end through
# ./evolve — begin/finish mutation slots, guardrails that teach, doctor
# recovery, and verify exposing hand-edited ledgers.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$ROOT/bin/init-workspace.sh" "$TMP/ws" > /dev/null
cd "$TMP/ws"
export HARNESS_STUB=1 EVOLVE_SEED=13

echo "== status on an empty lineage"
./evolve status | sed 's/^/  /'

echo "== autonomous warm-up + verify"
./evolve run 2 > /dev/null 2>&1
./evolve verify | sed 's/^/  /'

echo "== agent-as-mutator: begin -> edit -> finish"
./evolve gen begin | sed 's/^/  /'
test -f .evolve-gen.json

echo "-- run is refused while a generation is pending"
if ./evolve run 1 > /dev/null 2>&1; then echo "FAIL: run during pending"; exit 1; fi

echo "-- FROZEN edits are reverted with a teaching error"
echo "# sneak" >> FROZEN/eval.sh
if ./evolve gen finish --note x > "$TMP/frozen_err" 2>&1; then
  echo "FAIL: finish accepted a FROZEN edit" >&2; exit 1
fi
grep -q "FROZEN" "$TMP/frozen_err" && grep -q "re-run" "$TMP/frozen_err"
git diff --quiet -- FROZEN || { echo "FAIL: FROZEN edit not reverted" >&2; exit 1; }

echo "-- out-of-scope edits are named and refused"
echo "# sneak" >> driver.py
if ./evolve gen finish --note x > "$TMP/scope_err" 2>&1; then
  echo "FAIL: finish accepted an out-of-scope edit" >&2; exit 1
fi
grep -q "driver.py" "$TMP/scope_err"
git checkout -q -- driver.py

echo "-- a real candidate mutation goes through the whole pipeline"
python3 - <<'PY'
import json
p = json.load(open("candidate/params.json"))
p["temperature"] = 0.42
json.dump(p, open("candidate/params.json", "w"), indent=1)
PY
./evolve gen finish --note "agent: set temperature=0.42" --predict task_1 | sed 's/^/  /'
python3 - <<'PY'
import json
nodes = [json.loads(l) for l in open("archive.jsonl") if l.strip()]
last = nodes[-1]
assert last["note"] == "agent: set temperature=0.42", last["note"]
assert last["predicted_fixes"] == ["task_1"]
assert "candidate/params.json" in last["mutated"]
print(f"  ledger OK: gen {last['genid']} carries the agent's note, prediction, and diff")
PY
test ! -f .evolve-gen.json

echo "== abort restores the tree"
./evolve gen begin > /dev/null
echo "junk" >> candidate/notes.md
./evolve gen abort | sed 's/^/  /'
git diff --quiet || { echo "FAIL: abort left a dirty tree" >&2; exit 1; }

echo "== doctor: reverts orphan edits, completes interrupted generations"
echo "stray" >> candidate/notes.md
./evolve doctor | sed 's/^/  /'
git diff --quiet || { echo "FAIL: doctor left the tree dirty" >&2; exit 1; }
BEFORE="$(wc -l < archive.jsonl)"
head -n -1 archive.jsonl > "$TMP/cut" && mv "$TMP/cut" archive.jsonl  # simulate a crash after tag, before record
./evolve doctor | sed 's/^/  /'
test "$(wc -l < archive.jsonl)" -eq "$BEFORE" || { echo "FAIL: doctor did not complete the gen" >&2; exit 1; }
./evolve verify > /dev/null

echo "== verify exposes a hand-edited ledger"
python3 - <<'PY'
import json
lines = open("archive.jsonl").readlines()
n = json.loads(lines[-1]); n["score"] = 0.99
lines[-1] = json.dumps(n) + "\n"
open("archive.jsonl", "w").writelines(lines)
PY
if ./evolve verify > "$TMP/verify_out" 2>&1; then
  echo "FAIL: verify passed a forged ledger" >&2; exit 1
fi
grep -q "edited by hand" "$TMP/verify_out" && echo "  caught: $(grep -m1 FAIL "$TMP/verify_out")"

echo "== status/show --json are parseable"
python3 -c "import json,subprocess; json.loads(subprocess.run(['./evolve','status','--json'],capture_output=True,text=True).stdout)"
python3 -c "import json,subprocess; json.loads(subprocess.run(['./evolve','show','1','--json'],capture_output=True,text=True).stdout)"
echo "  ok"

echo
echo "skill_cli: PASS"
