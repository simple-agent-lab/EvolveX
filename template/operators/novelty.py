#!/usr/bin/env python3
"""novelty — reject near-duplicate mutations before burning canonical eval
budget (design v0.4 §06-B3, ShinkaEvolve-style).

Compares the working-tree diff (this mutation, pre-commit) against the diffs
of the last N accepted generations using difflib sequence similarity — no
embedding service needed; an embedding variant can replace `similarity()`
(this operator is evolvable). Above EVOLVE_NOVELTY_THRESHOLD (default 0.98)
the mutation is bounced back to mutate.py (driver retries ≤2 with --attempt).
"""
import difflib
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import operator_main, read_archive, ws_path  # noqa: E402
from FROZEN.contracts.protocol import NoveltyOutput  # noqa: E402

N_RECENT = 5


def git_diff(*args) -> str:
    p = subprocess.run(["git", "diff", *args], cwd=ws_path(),
                       capture_output=True, text=True)
    return p.stdout


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


@operator_main("novelty")
def main(args):
    current = git_diff()  # working tree vs parent checkout (mutation, pre-commit)
    threshold = float(os.environ.get("EVOLVE_NOVELTY_THRESHOLD", "0.98"))

    best_sim, best_gen = 0.0, None
    recent = [n for n in read_archive() if n.get("parent") is not None][-N_RECENT:]
    for n in recent:
        past = git_diff(f"gen/{n['parent']}", f"gen/{n['genid']}")
        sim = similarity(current, past)
        if sim > best_sim:
            best_sim, best_gen = sim, n["genid"]

    accept = best_sim <= threshold
    return NoveltyOutput(
        novelty=round(1.0 - best_sim, 4),
        accept=accept,
        extras={"threshold": threshold, "most_similar_gen": best_gen,
                "hint": None if accept else
                f"too similar to gen/{best_gen} (sim={best_sim:.3f}) — change direction"},
    )


if __name__ == "__main__":
    main()
