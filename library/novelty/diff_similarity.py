"""Novelty by diff similarity: reject a candidate edit that near-duplicates a
recent accepted one.

Compares this generation's candidate diff (the checkout's uncommitted changes
against its parent) with the diffs of the last `history_k` accepted generations.
`novelty = 1 - max_similarity`; the candidate edit is accepted only when the closest
prior diff is below `threshold` similarity (default `EVOLVE_NOVELTY_THRESHOLD`,
0.98). An empty diff (no-op candidate edit) is treated as a duplicate.
"""

import difflib
import json
import os
import subprocess
from pathlib import Path

from evolve.frozen import sdk
from evolve.frozen.config import Config, integer, number
from evolve.frozen.interfaces import NoveltyOperator, NoveltyResult, OperatorContext


def _threshold_default() -> float:
    try:
        return float(os.environ.get("EVOLVE_NOVELTY_THRESHOLD", "0.98"))
    except ValueError as error:
        raise ValueError("EVOLVE_NOVELTY_THRESHOLD must be a finite number between 0 and 1") from error


CONFIG = Config(
    {
        "threshold": number(default=_threshold_default(), minimum=0, maximum=1),
        "history_k": integer(default=8, minimum=1),
    }
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "no diagnostic output"
        raise RuntimeError(f"git {' '.join(args)} failed with exit code {result.returncode}: {detail}")
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
    sdk.main(DiffSimilarityNovelty, config_schema=CONFIG)
