"""GEPA-style parent selection from per-task Pareto frontiers.

The coverage-pruning rule follows GEPA's MIT-licensed `gepa_utils.py`; see NOTICE.
"""

# ruff: noqa: E402

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evolve.evaluation.evidence import TaskVectorError, normalize_task_vector
from evolve.frozen import sdk
from evolve.frozen.interfaces import ArchiveView, OperatorContext, SelectOperator, SelectResult
from library.select._config import SELECT_CONFIG as CONFIG


def _task_scores(row: dict[str, Any]) -> dict[str, float]:
    try:
        vector = normalize_task_vector(row.get("task_vector"))
    except TaskVectorError:
        return {}
    scores: dict[str, float] = {}
    for task_id, task in vector["tasks"].items():
        values = [
            float(trial["reward"])
            for trial in task["trials"]
            if trial.get("status") == "benchmark_complete"
            and isinstance(trial.get("reward"), (int, float))
            and not isinstance(trial.get("reward"), bool)
        ]
        if values and len(values) == len(task["trials"]):
            scores[str(task_id)] = sum(values) / len(values)
    return scores


def pareto_frontiers(parents: list[dict[str, Any]]) -> tuple[dict[str, set[str]], dict[str, dict[str, float]]]:
    by_candidate = {str(row["genid"]): _task_scores(row) for row in parents}
    task_ids = sorted({task_id for scores in by_candidate.values() for task_id in scores})
    fronts: dict[str, set[str]] = {}
    for task_id in task_ids:
        observed = {genid: scores[task_id] for genid, scores in by_candidate.items() if task_id in scores}
        if observed:
            best = max(observed.values())
            fronts[task_id] = {genid for genid, score in observed.items() if score == best}
    return fronts, by_candidate


def _is_dominated(candidate: str, survivors: set[str], fronts: dict[str, set[str]]) -> bool:
    containing = [front for front in fronts.values() if candidate in front]
    return all(front & survivors for front in containing)


def remove_dominated(
    fronts: dict[str, set[str]],
    aggregate_scores: dict[str, float],
) -> dict[str, set[str]]:
    """Retain a minimal coverage set using GEPA's score-ordered pruning rule."""
    candidates = sorted(
        {candidate for front in fronts.values() for candidate in front},
        key=lambda candidate: (aggregate_scores.get(candidate, 0.0), candidate),
    )
    dominated: set[str] = set()
    changed = True
    while changed:
        changed = False
        for candidate in candidates:
            if candidate in dominated:
                continue
            survivors = set(candidates) - dominated - {candidate}
            if _is_dominated(candidate, survivors, fronts):
                dominated.add(candidate)
                changed = True
                break
    return {task_id: front - dominated for task_id, front in fronts.items()}


def pareto_weights(parents: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, Any]]:
    fronts, task_scores = pareto_frontiers(parents)
    aggregate = {
        str(row["genid"]): float(row.get("score", 0.0))
        for row in parents
        if isinstance(row.get("score"), (int, float)) and not isinstance(row.get("score"), bool)
    }
    reduced = remove_dominated(fronts, aggregate) if fronts else {}
    weights: dict[str, int] = {}
    for front in reduced.values():
        for candidate in front:
            weights[candidate] = weights.get(candidate, 0) + 1
    diagnostics = {
        "frontiers": {task_id: sorted(front) for task_id, front in fronts.items()},
        "reduced_frontiers": {task_id: sorted(front) for task_id, front in reduced.items()},
        "weights": weights,
        "aggregate_scores": aggregate,
        "task_scores": task_scores,
    }
    return weights, diagnostics


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


class ParetoSelect(SelectOperator):
    def pick(self, archive: ArchiveView, ctx: OperatorContext) -> SelectResult:
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("pareto selection found no valid parents")
        weights, diagnostics = pareto_weights(parents)
        if weights:
            candidates = sorted(weights)
            chosen = ctx.rng.choices(
                candidates,
                weights=[weights[candidate] for candidate in candidates],
                k=max(1, ctx.fan_out),
            )
            diagnostics["fallback"] = False
        else:
            scored = [
                row
                for row in parents
                if isinstance(row.get("score"), (int, float)) and not isinstance(row.get("score"), bool)
            ]
            if not scored:
                raise SystemExit("pareto selection found no per-task or aggregate scores")
            best = max(scored, key=lambda row: float(row["score"]))
            chosen = [str(best["genid"])] * max(1, ctx.fan_out)
            diagnostics["fallback"] = True
        diagnostics["selected"] = chosen
        _write_json(ctx.run_dir / "pareto.json", diagnostics)
        return SelectResult(parents=chosen)


if __name__ == "__main__":
    sdk.main(ParetoSelect, config_schema=CONFIG)
