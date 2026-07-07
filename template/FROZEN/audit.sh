#!/usr/bin/env bash
# FROZEN — trace audit (lands at M3+; load-bearing on the weights path from M5).
# Contract when wired: triggered on best-ever updates or anomalous score jumps;
# an out-of-loop auditor reads the gen's diff + trajectories and rules
# "real capability" vs "exploit", writing audit=clean|exploit into the stamp.
# Exploit-flagged gens: trajectories are excluded from training data (decontam).
echo "audit lands at M3+ — stamps default to audit=clean until then" >&2
exit 3  # EXIT_NOT_WIRED
