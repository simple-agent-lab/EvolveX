import hashlib
import importlib.util
import json
import random
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ahe_trace_analysis", ROOT / "library" / "rollout" / "ahe_trace_analysis.py")
assert SPEC is not None and SPEC.loader is not None
AHE_ROLLOUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AHE_ROLLOUT)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _vector(outcomes: dict[str, list[int]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "tasks": {
            task_id: {
                "trials": [
                    {"trial": index, "status": "complete", "reward": float(reward)}
                    for index, reward in enumerate(rewards)
                ]
            }
            for task_id, rewards in outcomes.items()
        },
    }


def _write_artifacts(workspace: Path, generation: str, task_ids: list[str]) -> dict[str, str]:
    artifact_dir = workspace / "runs" / f"gen-{generation}" / "eval" / "artifacts"
    files = []
    for task_id in task_ids:
        trace = artifact_dir / f"{task_id}.md"
        trace.parent.mkdir(parents=True, exist_ok=True)
        trace.write_text(f"training trace for {task_id}\n")
        files.append({"path": f"artifacts/{task_id}.md", "sha256": _sha256(trace)})
    index = artifact_dir.parent / "evaluation_artifacts.json"
    index.write_text(
        json.dumps(
            {
                "jobs_dir": str(artifact_dir.parent.resolve()),
                "trials": [{"task_name": task_id, "files": [files[index]]} for index, task_id in enumerate(task_ids)],
            }
        )
    )
    return {"path": str(index.relative_to(workspace)), "sha256": _sha256(index)}


def test_ahe_rollout_parallel_trace_analysis_is_hashed_and_isolated(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    checkout = workspace / "candidate-checkout"
    run_dir = workspace / "runs" / "gen-2"
    checkout.mkdir(parents=True)
    task_ids = ["failed-task", "regressed-task", "risk-task", "stable-pass"]
    grandparent_artifacts = _write_artifacts(workspace, "0", task_ids)
    parent_artifacts = _write_artifacts(workspace, "1", task_ids)

    manifest = workspace / "runs" / "gen-1" / "record" / "ahe_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"changes": [{"id": "change-1", "predicted_fixes": ["failed-task"], "risk_tasks": ["risk-task"]}]}))
    rows = [
        {
            "genid": "0",
            "task_vector": _vector({"failed-task": [0, 0], "regressed-task": [1, 1], "risk-task": [1, 1], "stable-pass": [1, 1]}),
            "evaluation_artifacts": grandparent_artifacts,
        },
        {
            "genid": "1",
            "parent": "0",
            "task_vector": _vector({"failed-task": [0, 0], "regressed-task": [1, 0], "risk-task": [1, 1], "stable-pass": [1, 1]}),
            "evaluation_artifacts": parent_artifacts,
            "ahe_manifest_path": str(manifest.relative_to(workspace)),
            "ahe_manifest_sha256": _sha256(manifest),
        },
    ]
    (workspace / "archive.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))

    active_debuggers = 0
    max_active_debuggers = 0
    calls: list[dict[str, object]] = []
    lock = threading.Lock()

    def fake_run_meta_agent(*, workspace: Path, prompt: str, config: dict, env_overrides: dict):
        nonlocal active_debuggers, max_active_debuggers
        role = env_overrides["EVOLVE_SOURCE_AGENT_ROLE"]
        call = {"workspace": workspace, "prompt": prompt, "config": config, "env": env_overrides}
        calls.append(call)
        if role == "debugger":
            with lock:
                active_debuggers += 1
                max_active_debuggers = max(max_active_debuggers, active_debuggers)
            time.sleep(0.02)
            with lock:
                active_debuggers -= 1
            return SimpleNamespace(stdout=f"detail report for {workspace.name}\n")
        return SimpleNamespace(stdout="overview report\n")

    monkeypatch.setattr(AHE_ROLLOUT, "run_meta_agent", fake_run_meta_agent)
    ctx = OperatorContext(
        workspace=workspace,
        checkout=checkout,
        run_dir=run_dir,
        genid="2",
        parent="1",
        round=None,
        fan_out=1,
        config={"debugger": {"command": "fake-debugger", "workers": 99, "attempts": 1, "control_count": 1, "seed": 7}},
        rng=random.Random(0),
    )

    result = AHE_ROLLOUT.AheTraceAnalysisRollout().rollout(checkout, ctx)

    assert json.loads((run_dir / "rollout/analysis/selection.json").read_text()) == {
        "generation": "2",
        "tasks": {
            "failed-task": ["failure"],
            "regressed-task": ["regression"],
            "risk-task": ["predicted_risk"],
            "stable-pass": ["successful_control"],
        },
    }
    assert (run_dir / "rollout/analysis/detail/failed-task.md").exists()
    assert (run_dir / "rollout/analysis/overview.md").exists()
    assert json.loads((run_dir / "rollout/attribution.json").read_text())["summary"]
    assert max_active_debuggers <= 5
    assert all(call["workspace"] != checkout for call in calls)
    for call in calls:
        env = call["env"]
        assert all(env[name] is None for name in AHE_ROLLOUT.PROXY_REMOVALS)
    assert result.summary["analyzed"] == 4
    assert "rollout/analysis/overview.md" in result.artifacts


def test_ahe_rollout_selection_honors_zero_controls() -> None:
    selection = AHE_ROLLOUT._selection(
        {"failed": "fail", "passing": "pass"},
        {"improved": [], "regressed": [], "unchanged": [], "unknown": []},
        [],
        _vector({"failed": [0, 0], "passing": [1, 1]}),
        {"control_count": 0, "seed": 0},
        2,
    )

    assert selection["control"] == []


def test_ahe_rollout_caps_parallel_debuggers_at_five(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    checkout = workspace / "candidate-checkout"
    run_dir = workspace / "runs" / "gen-2"
    checkout.mkdir(parents=True)
    task_ids = [f"failed-{index}" for index in range(6)]
    artifacts = _write_artifacts(workspace, "1", task_ids)
    (workspace / "archive.jsonl").write_text(
        json.dumps({"genid": "1", "task_vector": _vector({task_id: [0, 0] for task_id in task_ids}), "evaluation_artifacts": artifacts})
        + "\n"
    )

    active = 0
    maximum = 0
    lock = threading.Lock()

    def fake_run_meta_agent(*, workspace: Path, prompt: str, config: dict, env_overrides: dict):
        nonlocal active, maximum
        if env_overrides["EVOLVE_SOURCE_AGENT_ROLE"] == "debugger":
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.02)
            with lock:
                active -= 1
        return SimpleNamespace(stdout="report\n")

    monkeypatch.setattr(AHE_ROLLOUT, "run_meta_agent", fake_run_meta_agent)
    ctx = OperatorContext(
        workspace=workspace,
        checkout=checkout,
        run_dir=run_dir,
        genid="2",
        parent="1",
        round=None,
        fan_out=1,
        config={"debugger": {"command": "fake-debugger", "workers": 99, "control_count": 0}},
        rng=random.Random(0),
    )

    AHE_ROLLOUT.AheTraceAnalysisRollout().rollout(checkout, ctx)

    assert maximum == 5
