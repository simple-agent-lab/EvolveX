#!/usr/bin/env python3
"""lineage-report — read-only health & attribution report over a workspace
(design §06-B2 population health + §06-C Tier-1 lineage attribution).

  - population : per-gen scores, champion, valid-parent ratio
  - diversity  : mean pairwise Jaccard distance over valid parents'
                 task_vectors (falling trend = collapse warning)
  - attribution: for every operator-mutation event, mean score of its
                 descendants (within horizon H) vs its siblings' descendants —
                 the sibling lineages are the natural control group. Observational
                 (confounded by candidate changes riding along); a REFERENCE
                 signal, never an admission verdict — that's meta_eval's job.

Usage: lineage-report.py <workspace> [--horizon 5]
"""
import argparse
import json
import statistics
import sys
from pathlib import Path


def jaccard_distance(a: str, b: str) -> float:
    sa = {i for i, c in enumerate(a) if c == "1"}
    sb = {i for i, c in enumerate(b) if c == "1"}
    union = sa | sb
    return 1.0 - (len(sa & sb) / len(union)) if union else 0.0


def descendants(nodes, root, horizon):
    kids, out, frontier = {}, [], [root]
    for n in nodes:
        if n["parent"] is not None:
            kids.setdefault(n["parent"], []).append(n["genid"])
    for _ in range(horizon):
        frontier = [c for g in frontier for c in kids.get(g, [])]
        out.extend(frontier)
        if not frontier:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("workspace")
    ap.add_argument("--horizon", type=int, default=5)
    a = ap.parse_args()
    ws = Path(a.workspace)

    nodes = [json.loads(l) for l in (ws / "archive.jsonl").read_text().splitlines()
             if l.strip()]
    by_id = {n["genid"]: n for n in nodes}

    print(f"# lineage report — {ws.name} ({len(nodes)} gens)")
    valid = [n for n in nodes if n["valid_parent"]]
    best = max(nodes, key=lambda n: n["score"])
    print(f"\n## population\nchampion: gen {best['genid']} @ {best['score']}"
          f"  |  valid parents: {len(valid)}/{len(nodes)}"
          f"  |  pending audits: {sum(1 for n in nodes if n['audit'] == 'pending')}")

    vecs = [n["task_vector"] for n in valid if n.get("task_vector")]
    if len(vecs) >= 2:
        dists = [jaccard_distance(vecs[i], vecs[j])
                 for i in range(len(vecs)) for j in range(i + 1, len(vecs))]
        print(f"\n## diversity\nmean pairwise Jaccard distance (valid parents): "
              f"{statistics.mean(dists):.3f}"
              + ("   <- collapse warning" if statistics.mean(dists) < 0.1 else ""))

    events = [n for n in nodes if n.get("operator_diff")]
    print(f"\n## operator-mutation attribution (horizon {a.horizon}, observational)")
    if not events:
        print("no operator-mutation events in this lineage")
    for e in events:
        mine = [by_id[d]["score"] for d in descendants(nodes, e["genid"], a.horizon)]
        siblings = [n for n in nodes
                    if n["parent"] == e["parent"] and n["genid"] != e["genid"]]
        theirs = [by_id[d]["score"] for s in siblings
                  for d in descendants(nodes, s["genid"], a.horizon)]
        me = statistics.mean(mine) if mine else None
        them = statistics.mean(theirs) if theirs else None
        credit = (f"{me - them:+.3f}" if me is not None and them is not None else "n/a")
        print(f"gen {e['genid']} [{e['operator_diff']}]"
              f"{' REVERTED' if e['operator_reverted'] else ''}: "
              f"descendants n={len(mine)} mean={me if me is None else round(me, 3)}"
              f" vs sibling-lineages n={len(theirs)} "
              f"mean={them if them is None else round(them, 3)}"
              f"  credit={credit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
