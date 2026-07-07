#!/usr/bin/env bash
# preflight — fail fast before burning a generation (infra guarantees).
# M0: python3/git present, stub mode confirmed.
# M1 adds: harbor version pin matches harness.env, docker reachable, API key
# set, dataset.pin resolvable.
set -euo pipefail

command -v python3 >/dev/null || { echo "preflight: python3 not found" >&2; exit 1; }
command -v git >/dev/null || { echo "preflight: git not found" >&2; exit 1; }

if [[ "${HARNESS_STUB:-0}" != "1" ]]; then
  echo "preflight: real harbor harness lands at M1 — set HARNESS_STUB=1" >&2
  exit 1
fi
