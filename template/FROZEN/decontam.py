#!/usr/bin/env python3
"""FROZEN — training-data decontamination + stamping (invariant #4, lands at M5).

Contract when wired:
  input : a distill manifest (jsonl; each sample traces to genid/task_id/trajectory_hash)
  checks: every sample's task_id is in splits.json["dev"];
          the source gen's ledger audit field is "clean" (exploit trajectories never train);
  output: the manifest gains "decontam_stamp"; train engines REJECT unstamped manifests.

distill.py is evolvable; this gate is not reachable by it.
"""
import sys

print("decontam lands at M5 — no training data may be stamped before then", file=sys.stderr)
sys.exit(2)
