#!/usr/bin/env python3
"""novelty — reject near-duplicate mutations before burning canonical eval
budget (design v0.4 §06-B3, ShinkaEvolve-style).

M0: pass-through stub (always accept). M3 wires embeddings of diff+note
against the last N accepted mutations; similarity above threshold bounces the
mutation back to mutate.py (≤2 retries) with a "too similar to gen/X" hint.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import operator_main  # noqa: E402
from FROZEN.contracts.protocol import NoveltyOutput  # noqa: E402


@operator_main("novelty")
def main(args):
    return NoveltyOutput(novelty=1.0, accept=True, extras={"status": "stub-until-M3"})


if __name__ == "__main__":
    main()
