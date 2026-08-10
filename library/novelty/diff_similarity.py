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
from evolve.frozen.interfaces import NoveltyOperator, NoveltyResult, OperatorContext
from library._shared.config import config_object, positive_int, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, {"threshold", "history_k"})
    threshold = config.get("threshold")
    if "threshold" in config and (isinstance(threshold, bool) or not isinstance(threshold, (int, float))):
        raise ValueError("threshold must be a finite number between 0 and 1")
    threshold = threshold if "threshold" in config else os.environ.get("EVOLVE_NOVELTY_THRESHOLD", 0.98)
    try:
        normalized_threshold = float(threshold)
    except ValueError as error:
        raise ValueError("threshold must be a finite number between 0 and 1") from error
    if not 0 <= normalized_threshold <= 1 or normalized_threshold in {float("inf"), float("-inf")}:
        raise ValueError("threshold must be a finite number between 0 and 1")
    return {
        "threshold": normalized_threshold,
        "history_k": positive_int(config, "history_k", 8),
    }


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
    sdk.main(DiffSimilarityNovelty, validate_config=validate_config)
