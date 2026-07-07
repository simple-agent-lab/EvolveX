#!/usr/bin/env python3
"""gate — evolvable judgement over the frozen score (design v0.4 §02 step 8).

Default: "open" — anything that produced a clean stamp is a valid parent.
Bad gates can pollute the population but never the fitness signal (protected
by the frozen stamp + best-ever rules), so err loose rather than fake-strict.

Variants: hillclimb / elitist+rollback / valid-parent / task-stability.
Reads only the frozen stamp — never a score argument.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import operator_main, read_json, ws_path  # noqa: E402
from FROZEN.contracts.protocol import GateOutput  # noqa: E402


@operator_main("gate")
def main(args):
    stamp = read_json(ws_path("runs", f"gen-{args.gen}", "stamp.json"))
    if stamp is None:
        return GateOutput(status="discard", valid_parent=False,
                          extras={"gate": "open", "reason": "no frozen stamp"})
    ok = stamp.get("audit") == "clean" and isinstance(stamp.get("score"), (int, float))
    return GateOutput(status="keep" if ok else "discard", valid_parent=bool(ok),
                      extras={"gate": "open"})


if __name__ == "__main__":
    main()
