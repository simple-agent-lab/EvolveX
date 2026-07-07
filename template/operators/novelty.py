#!/usr/bin/env python3
"""novelty — reject near-duplicate mutations before burning canonical eval budget
(design v0.4 §06-B3, ShinkaEvolve-style).

M0: pass-through stub (always accept). M3 wires embeddings of diff+note against
the last N accepted mutations; similarity above threshold bounces the mutation
back to mutate.py (≤2 retries) with a "too similar to gen/X, change direction"
hint — canonical eval is the most expensive resource in the loop.

Contract: prints JSON {"novelty": float, "accept": bool}.
"""
import argparse
import json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", type=int, required=True)
    ap.add_argument("--parent", type=int, required=True)
    ap.parse_args()
    print(json.dumps({"novelty": 1.0, "accept": True, "status": "stub-until-M3"}))


if __name__ == "__main__":
    main()
