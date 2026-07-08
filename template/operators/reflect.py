#!/usr/bin/env python3
"""reflect — turn this generation's outcome into durable, cross-lineage memory
(insight pool, design §06-A). Three jobs per gen:

  1. distill : verified/refuted predictions (settled by record's falsification
               closure) become tactic/pitfall entries — itemized, with evidence
               genids, via ADD/UPDATE delta ops. NEVER a full rewrite.
  2. credit  : insights this gen's mutate used get support (score improved
               over parent) or refute (score dropped) — without this backfill
               the playbook bloats into notes nobody trusts; with it, bad
               experience is evicted automatically.
  3. curate  : cap active entries (EVOLVE_PLAYBOOK_CAP, default 80), retire
               lowest utility = support - refute (ties: oldest last_used).

M2 default is rule-based distillation; an LLM distiller can replace step 1
(this operator is evolvable) — the fold/append primitives stay in oplib.
"""
import os

from FROZEN.contracts.oplib import (operator_main, playbook_active, playbook_append,  # noqa: E402
                                    playbook_state, read_archive)
from FROZEN.contracts.protocol import ReflectOutput  # noqa: E402


def upsert(state, ops, *, eid, etype, claim, tasks, gen, delta_support=0, delta_refute=0):
    prev = state.get(eid)
    entry = {
        "id": eid,
        "type": etype,
        "claim": claim,
        "target_tasks": tasks,
        "evidence": sorted(set((prev or {}).get("evidence", []) + [gen])),
        "support": (prev or {}).get("support", 0) + delta_support,
        "refute": (prev or {}).get("refute", 0) + delta_refute,
        "status": "active",
        "born_gen": (prev or {}).get("born_gen", gen),
        "last_used": gen,
    }
    op = dict(entry, op=("UPDATE" if prev else "ADD"))
    state[eid] = entry
    ops.append(op)


@operator_main("reflect")
def main(args):
    nodes = read_archive()
    me = next((n for n in nodes if n["genid"] == args.gen), None)
    if me is None:
        return ReflectOutput(ops=[], extras={"reason": "gen not in ledger yet"})
    parent = next((n for n in nodes if n["genid"] == me.get("parent")), None)

    state = playbook_state()
    ops = []

    # 1. distill: settled predictions -> tactic / pitfall entries
    for fix in me.get("verified_fixes", []):
        upsert(state, ops, eid=f"ins_fix_{fix}", etype="tactic",
               claim=f"a small mutation aimed at the {fix} failure cluster was "
                     f"verified to fix it (see the evidence gens' diffs)",
               tasks=[fix], gen=args.gen, delta_support=1)
    for fix in me.get("refuted_fixes", []):
        upsert(state, ops, eid=f"ins_miss_{fix}", etype="pitfall",
               claim=f"a mutation predicted to fix {fix} did not work — find new "
                     f"evidence before trying that direction again",
               tasks=[fix], gen=args.gen, delta_refute=1)

    # 2. credit backfill on the insights this gen's mutation consumed
    if parent is not None:
        improved = me["score"] > parent["score"]
        for eid in me.get("used_insights", []):
            prev = state.get(eid)
            if not prev:
                continue
            upsert(state, ops, eid=eid, etype=prev["type"], claim=prev["claim"],
                   tasks=prev.get("target_tasks", []), gen=args.gen,
                   delta_support=1 if improved else 0,
                   delta_refute=0 if improved else 1)

    # 3. curate: cap active entries, retire lowest utility
    cap = int(os.environ.get("EVOLVE_PLAYBOOK_CAP", "80"))
    active = playbook_active(state)
    if len(active) > cap:
        active.sort(key=lambda e: (e["support"] - e["refute"], e["last_used"]))
        for e in active[: len(active) - cap]:
            retired = dict(e, status="retired", op="RETIRE")
            state[e["id"]] = retired
            ops.append(retired)

    if ops:
        playbook_append(ops)
    return ReflectOutput(ops=ops, extras={"active_entries": len(playbook_active(state))})


if __name__ == "__main__":
    main()
