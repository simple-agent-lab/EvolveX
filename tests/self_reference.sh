#!/usr/bin/env bash
# M3 acceptance: the self-reference admission gate.
#   Case A: a benign operator change passes contracts + meta_eval replay and is
#           ADMITTED (ledger: operator_diff set, operator_reverted=false).
#   Case B: a broken operator change is caught by Tier-0 contracts and REVERTED
#           (operator file intact, candidate change survives, operator_reverted=true).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

make_self_ref_mutate() { # $1 = workspace, $2 = payload script appended to gate.py mutation
  cat > "$1/operators/mutate.py" <<EOF
#!/usr/bin/env python3
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import operator_main, ws_path
from FROZEN.contracts.protocol import MutateOutput

@operator_main("mutate")
def main(args):
    # candidate change (must survive either verdict)
    params_path = ws_path("candidate", "params.json")
    params = json.loads(params_path.read_text())
    params["retries"] = int(params.get("retries", 0)) + 1
    params.setdefault("tweak_seq", []).append(args.gen)
    params_path.write_text(json.dumps(params, indent=1) + "\n")
    # self-reference: touch operators/gate.py
    gate = ws_path("operators", "gate.py")
$2
    return MutateOutput(note=f"self-ref mutation gen {args.gen}",
                        predicted_fixes=[], used_insights=[],
                        cost={"tokens": 0, "eval_minutes": 0})

if __name__ == "__main__":
    main()
EOF
}

echo "== case A: benign operator change gets admitted"
"$ROOT/bin/init-workspace.sh" "$TMP/wsA" > /dev/null
make_self_ref_mutate "$TMP/wsA" '    gate.write_text(gate.read_text() + f"\n# benign tweak gen {args.gen}\n")'
( cd "$TMP/wsA" && git add -A && git commit -qm "test mutator" && git tag -f gen/0 )
( cd "$TMP/wsA" && HARNESS_STUB=1 EVOLVE_SEED=3 ./loop.sh 1 2>&1 | sed 's/^/  /' )
python3 - "$TMP/wsA" <<'PY'
import json, subprocess, sys
ws = sys.argv[1]
nodes = [json.loads(l) for l in open(f"{ws}/archive.jsonl") if l.strip()]
gen = nodes[-1]
adm = json.load(open(f"{ws}/runs/gen-{gen['genid']}/admission.json"))
assert adm["checked"] and adm["admitted"] and not adm["reverted"], adm
assert gen["operator_diff"] == "operators/gate.py", gen["operator_diff"]
assert gen["operator_reverted"] is False
tree = subprocess.run(["git", "show", f"gen/{gen['genid']}:operators/gate.py"],
                      cwd=ws, capture_output=True, text=True).stdout
assert "benign tweak" in tree, "admitted operator change missing from the snapshot"
print(f"  admitted: gen {gen['genid']} carries the operator change "
      f"(meta_eval old={adm['meta_eval']['old_best']} new={adm['meta_eval']['new_best']})")
PY

echo "== case B: broken operator change gets reverted, candidate change survives"
"$ROOT/bin/init-workspace.sh" "$TMP/wsB" > /dev/null
make_self_ref_mutate "$TMP/wsB" '    gate.write_text("this is not python at all(\n")'
( cd "$TMP/wsB" && git add -A && git commit -qm "test mutator" && git tag -f gen/0 )
( cd "$TMP/wsB" && HARNESS_STUB=1 EVOLVE_SEED=3 ./loop.sh 1 2>&1 | sed 's/^/  /' )
python3 - "$TMP/wsB" <<'PY'
import json, subprocess, sys
ws = sys.argv[1]
nodes = [json.loads(l) for l in open(f"{ws}/archive.jsonl") if l.strip()]
gen = nodes[-1]
adm = json.load(open(f"{ws}/runs/gen-{gen['genid']}/admission.json"))
assert adm["checked"] and not adm["admitted"] and adm["reverted"], adm
assert gen["operator_reverted"] is True
assert gen["operator_diff"] is None, "reverted operator change must not appear in the diff"
tree = subprocess.run(["git", "show", f"gen/{gen['genid']}:operators/gate.py"],
                      cwd=ws, capture_output=True, text=True).stdout
assert "not python" not in tree, "broken operator leaked into the snapshot"
params = subprocess.run(["git", "show", f"gen/{gen['genid']}:candidate/params.json"],
                        cwd=ws, capture_output=True, text=True).stdout
assert "tweak_seq" in params, "candidate change did not survive the operator revert"
print(f"  reverted: gen {gen['genid']} kept the candidate change, dropped the broken operator")
PY

echo
echo "self_reference: PASS"
