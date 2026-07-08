#!/usr/bin/env bash
# islands — population diversity via independent workspaces with periodic
# champion migration (design v0.4 §06-B4). Each island is its own workspace
# (own git archive, own ledger); every round the global champion's candidate/
# is injected into the other islands as a migration generation, which then
# competes under each island's own frozen ruler.
#
# Usage: islands.sh <base-dir> [n_islands] [rounds] [gens_per_round]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="${1:?usage: islands.sh <base-dir> [n_islands] [rounds] [gens_per_round]}"
N="${2:-3}"
ROUNDS="${3:-2}"
GENS="${4:-3}"

mkdir -p "$BASE"
for ((i = 0; i < N; i++)); do
  [[ -d "$BASE/island-$i" ]] || "$ROOT/bin/init-workspace.sh" "$BASE/island-$i" > /dev/null
done
echo "[islands] $N islands under $BASE"

run_py() { # run_py <workspace> <args...> — uv-managed python with fallback
  local ws="$1"; shift
  if command -v uv >/dev/null 2>&1; then
    PYTHONPATH="$ws" uv run --quiet --project "$ws" python3 "$@"
  else
    PYTHONPATH="$ws" python3 "$@"
  fi
}

for ((r = 1; r <= ROUNDS; r++)); do
  echo "[islands] round $r: $GENS gens per island"
  for ((i = 0; i < N; i++)); do
    # per-island seed salt: identical seeds would make every island walk the
    # same trajectory, defeating the whole point of the archipelago
    ( cd "$BASE/island-$i" \
      && EVOLVE_SEED="${EVOLVE_SEED:-pop}-island-$i" ./loop.sh "$GENS" 2>&1 \
        | sed "s/^/[island-$i] /" )
  done

  # find the global champion (by frozen best-ever, per island)
  CHAMP=-1; CHAMP_SCORE=-1; CHAMP_GEN=-1
  for ((i = 0; i < N; i++)); do
    read -r SCORE GEN < <(python3 -c '
import json, sys
b = json.load(open(sys.argv[1]))
print(b["score"], b["genid"])' "$BASE/island-$i/best_ever.json")
    echo "[islands] island-$i best: gen $GEN @ $SCORE"
    if python3 -c "import sys; sys.exit(0 if $SCORE > $CHAMP_SCORE else 1)"; then
      CHAMP=$i; CHAMP_SCORE=$SCORE; CHAMP_GEN=$GEN
    fi
  done
  echo "[islands] round $r champion: island-$CHAMP gen $CHAMP_GEN @ $CHAMP_SCORE"

  # migration window: inject the champion candidate into every other island
  if (( ROUNDS > 1 && r < ROUNDS )); then
    EXPORT="$(mktemp -d)"
    git -C "$BASE/island-$CHAMP" archive "gen/$CHAMP_GEN" candidate | tar -x -C "$EXPORT"
    for ((i = 0; i < N; i++)); do
      [[ $i -eq $CHAMP ]] && continue
      ( cd "$BASE/island-$i" \
        && run_py "$PWD" driver.py --inject "$EXPORT" 2>&1 | sed "s/^/[island-$i] /" )
    done
    rm -rf "$EXPORT"
  fi
done

echo "[islands] done"
