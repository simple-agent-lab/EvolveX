"""Novelty by diff similarity: reject a mutation that near-duplicates a recent
accepted one.

Compares this generation's mutation diff (the checkout's uncommitted changes
against its parent) with the diffs of the last `history_k` accepted generations.
`novelty = 1 - max_similarity`; the mutation is accepted only when the closest
prior diff is below `threshold` similarity (default `EVOLVE_NOVELTY_THRESHOLD`,
0.98). An empty diff (no-op mutation) is treated as a duplicate.
"""

# ruff: noqa: E402

import difflib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import NoveltyOperator, NoveltyResult, OperatorContext


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=False)
    return result.stdout


def _recent_accepted(workspace: Path, k: int) -> list[dict]:
    # Read the ledger directly (files are the source of truth); the newest k
    # accepted generations with a diffable (parent -> tag) lineage.
    path = workspace / "archive.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    accepted = [r for r in rows if r.get("valid_parent") is True and r.get("tag") and r.get("parent") is not None]
    return accepted[-k:]


class DiffSimilarityNovelty(NoveltyOperator):
    def assess(self, checkout: Path, ctx: OperatorContext) -> NoveltyResult:
        threshold = float(ctx.config.get("threshold", os.environ.get("EVOLVE_NOVELTY_THRESHOLD", 0.98)))
        history_k = int(ctx.config.get("history_k", 8))
        current = _git(checkout, "diff", "HEAD")
        if not current.strip():
            return NoveltyResult(novelty=0.0, accept=False)

        best = 0.0
        for row in _recent_accepted(ctx.workspace, history_k):
            past = _git(ctx.workspace, "diff", f"gen/{row['parent']}", str(row["tag"]))
            if past.strip():
                best = max(best, difflib.SequenceMatcher(None, current, past).ratio())
        return NoveltyResult(novelty=1.0 - best, accept=best < threshold)


if __name__ == "__main__":
    sdk.main(DiffSimilarityNovelty)
