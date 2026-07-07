#!/usr/bin/env python3
"""distill — trajectories -> training data (outer loop T2, lands at M5).

Contract when wired:
  input : runs/*/dev trajectories + archive.jsonl
  filter: task-level selection (a task succeeding qualifies its trajectory even
          in a low-scoring gen); near-duplicate dedup with per-task caps
          (keep the data distribution from collapsing onto easy tasks).
  output: SFT set (successful trajectories) + DPO pairs (same task,
          success vs failure) + manifests/<gen>.jsonl where every sample traces
          to (genid, task_id, trajectory_hash).
Manifests must then pass FROZEN/decontam.py (dev-split-only + audit-clean) —
train engines reject unstamped manifests. This operator is evolvable; that
gate is not reachable from here.
"""
import sys

print("distill lands at M5 — no trajectories to distill before the real harness (M1)", file=sys.stderr)
sys.exit(3)  # EXIT_NOT_WIRED; joins the protocol OPERATORS registry at M5
