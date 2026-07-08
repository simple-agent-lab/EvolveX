#!/usr/bin/env bash
# Agentic-mutate acceptance: the mutate operator spawns a file-editing agent
# (stubbed via EVOLVE_MUTATOR_CMD) that reads the brief, edits the candidate,
# and reports structured results; a rogue agent that touches FROZEN is
# contained by the driver's guards.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/good_agent.py" <<'EOF'
#!/usr/bin/env python3
"""stub agentic mutator: what a headless claude run would do, minus the LLM."""
import json, os
prompt = open(os.environ["MUTATION_PROMPT"]).read()
assert "mutation_report.json" in prompt, "brief must state the report contract"
assert "FROZEN" in prompt, "brief must state the prohibitions"
# the brief is a MAP, not a digest: it points at workspace files, never inlines them
assert "dev/feedback.json" in prompt and "insights/playbook.jsonl" in prompt, \
    "brief must point to the intel files"
assert json.load(open(f"runs/gen-{os.environ['MUTATION_GEN']}/dev/feedback.json")), \
    "the intel files must actually be readable from the workspace"
p = json.load(open("candidate/params.json"))
p["agentic_touch"] = p.get("agentic_touch", 0) + 1
json.dump(p, open("candidate/params.json", "w"), indent=1)
json.dump({"note": "stub-agent: bumped agentic_touch",
           "predicted_fixes": ["task_1"], "used_insights": []},
          open(os.environ["MUTATION_REPORT"], "w"))
EOF

cat > "$TMP/rogue_agent.py" <<'EOF'
#!/usr/bin/env python3
import json, os
with open("FROZEN/eval.sh", "a") as f:
    f.write("# hacked by rogue agent\n")
json.dump({"note": "rogue", "predicted_fixes": [], "used_insights": []},
          open(os.environ["MUTATION_REPORT"], "w"))
EOF
chmod +x "$TMP/good_agent.py" "$TMP/rogue_agent.py"

"$ROOT/bin/init-workspace.sh" "$TMP/ws" > /dev/null
cd "$TMP/ws"
export HARNESS_STUB=1 EVOLVE_SEED=21

echo "== warm-up (fixed), then two agentic generations via the stub agent"
./evolve run 1 > /dev/null 2>&1
EVOLVE_MUTATE_VARIANT=agent EVOLVE_MUTATOR_CMD="python3 $TMP/good_agent.py" \
  ./evolve run 2 > /dev/null 2>&1

python3 - <<'PY'
import json
nodes = [json.loads(l) for l in open("archive.jsonl") if l.strip()]
agentic = [n for n in nodes if n["note"].startswith("stub-agent")]
assert len(agentic) == 2, f"expected 2 agentic gens, got {len(agentic)}"
for n in agentic:
    assert "candidate/params.json" in n["mutated"], n["mutated"]
    assert n["predicted_fixes"] == ["task_1"]
params = json.load(open("candidate/params.json"))
assert params.get("agentic_touch") == 2
print(f"  agentic OK: gens {[n['genid'] for n in agentic]} carry the agent's edits, "
      f"note, and predictions")
PY
test -f "runs/gen-2/mutation_prompt.md" && echo "  brief persisted for inspection"

echo "== a rogue agent that edits FROZEN is contained (gen discarded, FROZEN intact)"
BEFORE="$(wc -l < archive.jsonl)"
EVOLVE_MUTATE_VARIANT=agent EVOLVE_MUTATOR_CMD="python3 $TMP/rogue_agent.py" \
  ./evolve run 1 > "$TMP/rogue_log" 2>&1 || true
grep -q "FROZEN" "$TMP/rogue_log" || { echo "FAIL: no FROZEN guard message" >&2; exit 1; }
test "$(wc -l < archive.jsonl)" -eq "$BEFORE" || { echo "FAIL: rogue gen entered the ledger" >&2; exit 1; }
git diff --quiet -- FROZEN || { echo "FAIL: FROZEN still dirty" >&2; exit 1; }
grep -q "hacked" FROZEN/eval.sh && { echo "FAIL: hack persisted in FROZEN" >&2; exit 1; }
echo "  contained: generation discarded, FROZEN restored"

echo "== missing report degrades gracefully"
EVOLVE_MUTATE_VARIANT=agent \
  EVOLVE_MUTATOR_CMD='python3 -c "import json;p=json.load(open(\"candidate/params.json\"));p[\"x\"]=1;json.dump(p,open(\"candidate/params.json\",\"w\"))"' \
  ./evolve run 1 > /dev/null 2>&1
python3 - <<'PY'
import json
last = [json.loads(l) for l in open("archive.jsonl") if l.strip()][-1]
assert "did not write mutation_report.json" in last["note"], last["note"]
print("  graceful: mutation recorded with an explanatory note")
PY

echo
echo "agentic_mutate: PASS"
