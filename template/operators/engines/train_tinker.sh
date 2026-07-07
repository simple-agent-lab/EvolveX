#!/usr/bin/env bash
# engine adapter — training engine (outer loop T4, wired at M6).
# Train-Engine contract (symmetric to the Harness contract):
#   input : base checkpoint ref + data manifest (MUST carry decontam_stamp) + recipe
#   output: new checkpoint ref (ckpts/gen-<id>) + train_metrics.json
# Unstamped manifests are rejected here (invariant #4 enforcement point).
echo "train engine adapter lands at M6" >&2
exit 2
