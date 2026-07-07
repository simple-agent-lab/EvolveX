#!/usr/bin/env bash
# driver-mode conductor: runs the 10-step inner loop N times (design v0.4 §02).
# agent mode replaces this driver with an orchestrating agent reading program.md.
set -euo pipefail
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$WS"
N="${1:-5}"
GIT=(git -c advice.detachedHead=false)

log() { printf '[loop] %s\n' "$*" >&2; }

frozen_digest() {
  find FROZEN -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1
}

next_id() {
  python3 -c 'import json; print(max((json.loads(l)["genid"] for l in open("archive.jsonl") if l.strip()), default=-1) + 1)'
}

json_field() { # json_field <file> <key>
  python3 -c 'import sys,json; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$1" "$2"
}

bash operators/preflight.sh

# ---- bootstrap: gen/0 needs a ledger entry before select can run
if [[ ! -s archive.jsonl ]]; then
  log "bootstrap: eval + record gen 0"
  "${GIT[@]}" checkout -q gen/0
  mkdir -p runs/gen-0
  FROZEN/eval.sh 0 > /dev/null
  bash FROZEN/stamp.sh 0 > /dev/null
  python3 operators/gate.py --gen 0 > runs/gen-0/gate.json
  python3 operators/record.py --gen 0 --genesis --note "genesis" > /dev/null
fi

for ((it = 0; it < N; it++)); do
  # (1) select parent
  PARENT="$(python3 operators/select.py | python3 -c 'import sys,json; print(json.load(sys.stdin)["parent"])')"
  GEN="$(next_id)"
  log "gen $GEN <- parent $PARENT"

  # (2) checkout parent snapshot (operators/candidate travel with lineage; untracked state persists)
  "${GIT[@]}" checkout -q "gen/$PARENT"
  mkdir -p "runs/gen-$GEN"
  FZ_BEFORE="$(frozen_digest)"

  # (3) dev rollout (advisory, never canonical)
  python3 operators/rollout.py --gen "$GEN" --parent "$PARENT" > "runs/gen-$GEN/rollout.json"
  # (4) mutate candidate (M3+: may include operators/ = self-reference)
  python3 operators/mutate.py --gen "$GEN" --parent "$PARENT" > "runs/gen-$GEN/mutate.json"
  # (5) novelty check (reject near-duplicate mutations before burning eval budget)
  python3 operators/novelty.py --gen "$GEN" --parent "$PARENT" > "runs/gen-$GEN/novelty.json"

  # FROZEN guard: mutation must never touch the frozen core
  if [[ "$(frozen_digest)" != "$FZ_BEFORE" ]]; then
    log "FROZEN modified by mutation — reverting, discarding gen $GEN"
    "${GIT[@]}" checkout -q -- .
    git clean -qfd candidate operators meta 2>/dev/null || true
    continue
  fi
  if [[ "$(json_field "runs/gen-$GEN/novelty.json" accept)" != "True" ]]; then
    log "novelty reject — discarding gen $GEN"
    "${GIT[@]}" checkout -q -- .
    git clean -qfd candidate operators meta 2>/dev/null || true
    continue
  fi

  # (6) commit + tag => new genome snapshot
  NOTE="$(json_field "runs/gen-$GEN/mutate.json" note)"
  git add -A
  git commit -qm "gen $GEN (parent $PARENT): $NOTE"
  git tag "gen/$GEN"

  # (self-reference admission gate FROZEN/meta_eval.sh + contracts lands at M3)

  # (7) canonical eval + frozen stamp (score/task_vector/CI — agent never touches these)
  FROZEN/eval.sh "$GEN" > /dev/null
  bash FROZEN/stamp.sh "$GEN" > /dev/null
  # (8) gate (evolvable judgement)
  python3 operators/gate.py --gen "$GEN" > "runs/gen-$GEN/gate.json"
  # (9) record: append ledger (frozen fields read from stamp, not from args)
  python3 operators/record.py --gen "$GEN" --parent "$PARENT" > /dev/null
  # (10) reflect: falsification check + playbook delta (stub until M2)
  python3 operators/reflect.py --gen "$GEN" > "runs/gen-$GEN/reflect.json"
done

BEST="$(python3 -c 'import json; print(json.load(open("best_ever.json"))["score"])' 2>/dev/null || echo 'n/a')"
log "done: $(wc -l < archive.jsonl | tr -d ' ') ledger entries, best-ever=$BEST"
