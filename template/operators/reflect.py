#!/usr/bin/env python3
"""reflect — falsification check + playbook delta update + credit backfill
(design v0.4 §06-A; real logic lands at M2, same milestone as llm-mutate —
they are producer/consumer and must ship together).

When wired, three jobs per gen:
  1. falsify : parent's predicted_fixes vs this gen's task_vector -> verified/refuted
  2. distill : 0–3 ADD/UPDATE/RETIRE delta ops on insights/playbook.jsonl
               (itemized entries with evidence genids; NEVER a full rewrite)
  3. curate + credit: dedup, cap active entries (~80), bump support/refute
               on insights this gen's mutate used.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import operator_main, ws_path  # noqa: E402
from FROZEN.contracts.protocol import ReflectOutput  # noqa: E402


@operator_main("reflect")
def main(args):
    playbook = ws_path("insights", "playbook.jsonl")
    playbook.parent.mkdir(parents=True, exist_ok=True)
    playbook.touch(exist_ok=True)
    return ReflectOutput(ops=[], extras={"status": "stub-until-M2"})


if __name__ == "__main__":
    main()
