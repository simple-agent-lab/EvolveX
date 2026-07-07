#!/usr/bin/env python3
"""gate — evolvable judgement over the frozen score (design v0.4 §02 step 8).

Default: "open" — anything that produced a clean stamp is a valid parent
(open-ended population; bad gates can pollute the population but never the
fitness signal, which is protected by the frozen stamp + best-ever rules).

Variants: hillclimb / elitist+rollback / valid-parent / task-stability.
Contract: reads runs/gen-<id>/stamp.json (never a score argument);
prints JSON {"status": "keep"|"discard", "valid_parent": bool}.
"""
import argparse
import json
import os

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", type=int, required=True)
    a = ap.parse_args()

    stamp_path = os.path.join(WS, "runs", f"gen-{a.gen}", "stamp.json")
    if not os.path.exists(stamp_path):
        print(json.dumps({"status": "discard", "valid_parent": False,
                          "gate": "open", "reason": "no frozen stamp"}))
        return
    stamp = json.load(open(stamp_path))
    ok = stamp.get("audit") == "clean" and isinstance(stamp.get("score"), (int, float))
    print(json.dumps({"status": "keep" if ok else "discard", "valid_parent": bool(ok),
                      "gate": "open"}))


if __name__ == "__main__":
    main()
