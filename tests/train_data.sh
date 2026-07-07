#!/usr/bin/env bash
# M5 acceptance: the training-data pipeline.
#   distill produces a fully traceable manifest from dev trajectories;
#   decontam stamps clean manifests and rejects (a) gate/sealed-task leakage,
#   (b) tampering after stamping; the train engine refuses unstamped data.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$ROOT/bin/init-workspace.sh" "$TMP/ws" > /dev/null
cd "$TMP/ws"
HARNESS_STUB=1 EVOLVE_SEED=9 ./loop.sh 6 > /dev/null 2>&1

echo "== distill produces a traceable manifest"
OUT="$(python3 operators/distill.py)"
MANIFEST="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['manifest'])" "$OUT")"
python3 - "$MANIFEST" <<'PY'
import hashlib, json, sys
manifest = sys.argv[1]
lines = [json.loads(l) for l in open(manifest) if l.strip()]
assert lines, "manifest is empty after 6 gens of dev rollouts"
sft = [l for l in lines if l["kind"] == "sft"]
assert sft, "no SFT samples"
for l in lines:
    srcs = [l["chosen"], l["rejected"]] if l["kind"] == "dpo" else [l]
    for s in srcs:
        traj = json.load(open(s["path"]))
        assert traj["trajectory_hash"] == s["trajectory_hash"], "hash broken"
        assert traj["task_id"] == l["task_id"]
print(f"  manifest OK: {len(sft)} sft, {len(lines) - len(sft)} dpo, all samples verified back to trajectories")
PY

echo "== decontam stamps the clean manifest; verify passes"
python3 FROZEN/decontam.py stamp "$MANIFEST" | sed 's/^/  /'
python3 FROZEN/decontam.py verify "$MANIFEST" | sed 's/^/  /'

echo "== train engine refuses an unstamped manifest"
cp "$MANIFEST" manifests/unstamped.jsonl
if bash operators/engines/train_tinker.sh base manifests/unstamped.jsonl operators/train/recipe.yaml out 2>/dev/null; then
  echo "FAIL: engine accepted unstamped data" >&2; exit 1
fi
echo "  refused as required"

echo "== decontam rejects gate-split leakage"
GATE_TASK="$(python3 -c "import json; print(json.load(open('FROZEN/splits.json'))['gate'][0])")"
cp "$MANIFEST" manifests/poisoned.jsonl
FIRST_TRAJ="$(python3 -c "
import json
l = json.loads(open('$MANIFEST').readline())
s = l['chosen'] if l['kind'] == 'dpo' else l
print(json.dumps({'kind': 'sft', 'task_id': $GATE_TASK, **{k: s[k] for k in ('genid','trajectory_hash','path')}}))")"
echo "$FIRST_TRAJ" >> manifests/poisoned.jsonl
if python3 FROZEN/decontam.py stamp manifests/poisoned.jsonl 2>"$TMP/err"; then
  echo "FAIL: decontam stamped a gate-task sample" >&2; exit 1
fi
grep -q "outside the dev split" "$TMP/err" && echo "  rejected: $(head -1 "$TMP/err")"

echo "== tampering after stamping is detected"
echo '{"kind":"sft","task_id":0,"genid":1,"trajectory_hash":"beef","path":"x"}' >> "$MANIFEST"
if python3 FROZEN/decontam.py verify "$MANIFEST" 2>"$TMP/err2"; then
  echo "FAIL: verify passed a tampered manifest" >&2; exit 1
fi
grep -q "STAMP MISMATCH" "$TMP/err2" && echo "  detected: $(head -1 "$TMP/err2")"

echo
echo "train_data: PASS"
