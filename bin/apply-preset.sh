#!/usr/bin/env bash
# apply-preset — install a repro-matrix config into a FRESH workspace
# (design §07: four systems = four configs, one framework path).
# Refuses to run mid-evolution: config.json travels with the lineage, so a
# mid-run switch must happen as a generation (a mutation), not out of band.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="${1:?usage: apply-preset.sh <workspace> <autoresearch|ahe|hyperagents|metaagent>}"
NAME="${2:?preset name}"
PRESET="$ROOT/presets/$NAME.json"

[[ -f "$PRESET" ]] || { echo "unknown preset: $NAME (have: $(ls "$ROOT/presets" | sed 's/\.json//' | tr '\n' ' '))" >&2; exit 1; }
[[ -s "$WS/archive.jsonl" ]] && { echo "refusing: $WS already has a lineage — switch presets via a mutation, not out of band" >&2; exit 1; }

cp "$PRESET" "$WS/config.json"
git -C "$WS" add config.json
git -C "$WS" commit -qm "preset: $NAME"
git -C "$WS" tag -f gen/0 > /dev/null
echo "preset $NAME applied to $WS (genesis re-tagged)"
