#!/usr/bin/env python3
"""reflect — falsification check + playbook delta update + credit backfill
(design v0.4 §06-A; real logic lands at M2, the same milestone as llm-mutate —
they are producer/consumer and must ship together).

Contract when wired, three jobs per gen:
  1. falsify : read parent's predicted_fixes, compare against this gen's
               task_vector, mark verified/refuted.
  2. distill : LLM proposes 0–3 ADD/UPDATE/RETIRE delta ops on
               insights/playbook.jsonl (itemized entries with evidence genids;
               NEVER a full rewrite — that path leads to context collapse).
  3. curate + credit: dedup by embedding, cap active entries (~80);
               bump support/refute on insights this gen's mutate used.

M0: ensures the playbook exists, emits an empty delta.
Contract: prints JSON {"ops": [...]}.
"""
import argparse
import json
import os

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", type=int, required=True)
    ap.parse_args()

    os.makedirs(os.path.join(WS, "insights"), exist_ok=True)
    playbook = os.path.join(WS, "insights", "playbook.jsonl")
    if not os.path.exists(playbook):
        open(playbook, "w").close()

    print(json.dumps({"ops": [], "status": "stub-until-M2"}))


if __name__ == "__main__":
    main()
