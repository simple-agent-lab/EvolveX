import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "library" / "select" / "pareto.py"
    spec = importlib.util.spec_from_file_location("gepa_pareto_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(genid: str, score: float, rewards: dict[str, float]):
    return {
        "genid": genid,
        "score": score,
        "task_vector": {
            "schema_version": 1,
            "tasks": {
                task_id: {"trials": [{"trial": 0, "status": "benchmark_complete", "reward": reward}]}
                for task_id, reward in rewards.items()
            },
        },
    }


def test_gepa_pareto_weights_count_surviving_task_front_coverage() -> None:
    module = _module()
    parents = [
        _row("a", 0.7, {"t1": 1, "t2": 1, "t3": 0}),
        _row("b", 0.4, {"t1": 1, "t2": 0, "t3": 0}),
        _row("c", 0.3, {"t1": 0, "t2": 0, "t3": 1}),
    ]

    weights, diagnostics = module.pareto_weights(parents)

    assert diagnostics["frontiers"] == {"t1": ["a", "b"], "t2": ["a"], "t3": ["c"]}
    assert diagnostics["reduced_frontiers"] == {"t1": ["a"], "t2": ["a"], "t3": ["c"]}
    assert weights == {"a": 2, "c": 1}


def test_gepa_pareto_ignores_noncanonical_task_trials() -> None:
    module = _module()
    row = _row("a", 1, {"task": 1})
    row["task_vector"]["tasks"]["task"]["trials"][0]["status"] = "infrastructure_failed"
    row["task_vector"]["tasks"]["task"]["trials"][0]["reward"] = None

    fronts, scores = module.pareto_frontiers([row])

    assert fronts == {}
    assert scores == {"a": {}}
