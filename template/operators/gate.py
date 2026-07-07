#!/usr/bin/env python3
"""gate — evolvable judgement over the frozen score (design §02 step 8).

Variants (config.json "gate"):
  open (default) — anything with a clean stamp is a valid parent (open-ended
        population; bad gates pollute the population, never the fitness
        signal — that's protected by the frozen stamp + best-ever rules)
  hillclimb — valid parent only if the score strictly improved on the parent
        (autoresearch/AHE-style greedy chain; discards plateaus)
  none — no judgement at all: keep everything (MetaAgent pure accumulation)

Reads only the frozen stamp + the ledger — never a score argument.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import config, operator_main, read_archive, read_json, ws_path  # noqa: E402
from FROZEN.contracts.protocol import GateOutput  # noqa: E402


@operator_main("gate")
def main(args):
    variant = config().get("gate", "open")
    stamp = read_json(ws_path("runs", f"gen-{args.gen}", "stamp.json"))

    if variant == "none":
        return GateOutput(status="keep", valid_parent=True, extras={"gate": "none"})

    if stamp is None:
        return GateOutput(status="discard", valid_parent=False,
                          extras={"gate": variant, "reason": "no frozen stamp"})
    clean = stamp.get("audit") == "clean" and isinstance(stamp.get("score"), (int, float))

    if variant == "hillclimb" and args.parent is not None:
        parent = next((n for n in read_archive() if n["genid"] == args.parent), None)
        improved = parent is None or stamp["score"] > parent["score"]
        ok = clean and improved
        return GateOutput(status="keep" if ok else "discard", valid_parent=ok,
                          extras={"gate": "hillclimb",
                                  "parent_score": parent and parent["score"]})

    return GateOutput(status="keep" if clean else "discard", valid_parent=bool(clean),
                      extras={"gate": "open"})


if __name__ == "__main__":
    main()
