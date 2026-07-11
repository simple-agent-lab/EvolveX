import copy
import hashlib
import importlib.util
import json
import random
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

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
        trace_name = task_id if "/" not in task_id and "\\" not in task_id else hashlib.sha256(task_id.encode()).hexdigest()
        trace = artifact_dir / f"{trace_name}.md"
        trace.parent.mkdir(parents=True, exist_ok=True)
        trace.write_text(f"training trace for {task_id}\n")
        files.append({"path": f"artifacts/{trace_name}.md", "sha256": _sha256(trace)})
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


def _scope(task_ids: list[str]) -> dict[str, object]:
    return {"task_set_hash": "fixture-task-set", "task_set_members": sorted(task_ids)}


def _rollout_config(task_ids: list[str], **overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "debugger": {"command": "fake-debugger"},
        "controls": {"successful": 0, "rotation_seed": 0},
        "training": {"task_names": sorted(task_ids)},
    }
    config.update(overrides)
    return config


def test_ahe_rollout_parallel_trace_analysis_is_hashed_and_isolated(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    checkout = workspace / "candidate-checkout"
    run_dir = workspace / "runs" / "gen-2"
    checkout.mkdir(parents=True)
    stale_report = run_dir / "rollout" / "analysis" / "detail" / "stale.md"
    stale_report.parent.mkdir(parents=True)
    stale_report.write_text("STALE REPORT MUST NOT BE READ\n")
    task_ids = ["failed-task", "regressed-task", "risk-task", "stable-pass"]
    grandparent_artifacts = _write_artifacts(workspace, "0", task_ids)
    parent_artifacts = _write_artifacts(workspace, "1", task_ids)

    manifest = workspace / "runs" / "gen-1" / "record" / "ahe_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"changes": [{"id": "change-1", "predicted_fixes": ["failed-task"], "risk_tasks": ["risk-task"]}]}))
    rows = [
        {
            "genid": "0",
            **_scope(task_ids),
            "task_vector": _vector({"failed-task": [0, 0], "regressed-task": [1, 1], "risk-task": [1, 1], "stable-pass": [1, 1]}),
            "evaluation_artifacts": grandparent_artifacts,
        },
        {
            "genid": "1",
            "parent": "0",
            **_scope(task_ids),
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
        config={
            "debugger": {"command": "fake-debugger", "workers": 99, "attempts": 1},
            "controls": {"successful": 1, "rotation_seed": 7},
            "training": {"task_names": sorted(task_ids)},
        },
        rng=random.Random(0),
    )

    result = AHE_ROLLOUT.AheTraceAnalysisRollout().rollout(checkout, ctx)

    assert json.loads((run_dir / "rollout/analysis/selection.json").read_text()) == {
        "generation": "2",
        "tasks": {
            "failed-task": ["failure"],
            "regressed-task": ["failure", "regression"],
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
    overview_call = next(call for call in calls if call["env"]["EVOLVE_SOURCE_AGENT_ROLE"] == "debugger_overview")
    assert "STALE REPORT MUST NOT BE READ" not in overview_call["prompt"]
    assert result.summary["analyzed"] == 4
    assert "rollout/analysis/overview.md" in result.artifacts


def test_ahe_rollout_selection_reads_successful_controls_from_controls_config() -> None:
    config = {
        "debugger": {"command": "fake-debugger", "workers": 5, "attempts": 3},
        "controls": {"successful": 1, "rotation_seed": 7},
    }

    selection = AHE_ROLLOUT._selection(
        {"alpha": "pass", "beta": "pass", "gamma": "pass", "delta": "pass"},
        {"improved": [], "regressed": [], "unchanged": [], "unknown": []},
        [],
        _vector({task_id: [1, 1] for task_id in ("alpha", "beta", "gamma", "delta")}),
        AHE_ROLLOUT._config_dict(config, "controls"),
        {},
        2,
    )

    assert selection["control"] == ["gamma"]


def test_ahe_rollout_selection_honors_zero_controls() -> None:
    selection = AHE_ROLLOUT._selection(
        {"failed": "fail", "passing": "pass"},
        {"improved": [], "regressed": [], "unchanged": [], "unknown": []},
        [],
        _vector({"failed": [0, 0], "passing": [1, 1]}),
        {"successful": 0, "rotation_seed": 0},
        {},
        2,
    )

    assert selection["control"] == []


def test_ahe_rollout_selection_respects_analyze_flags_with_true_defaults() -> None:
    states = {"failed": "fail", "partial": "partial", "regressed": "fail", "risk": "pass", "timeout": "unknown"}
    comparison = {"improved": [], "regressed": ["regressed"], "unchanged": [], "unknown": []}
    vector = _vector({"failed": [0, 0], "partial": [1, 0], "regressed": [0, 0], "risk": [1, 1]})
    vector["tasks"]["timeout"] = {"trials": [{"trial": 0, "status": "agent_timeout", "reward": None}]}

    defaults = AHE_ROLLOUT._selection(states, comparison, ["risk"], vector, {}, {}, 2)
    disabled = AHE_ROLLOUT._selection(
        states,
        comparison,
        ["risk"],
        vector,
        {},
        {"failures": False, "regressions": False, "timeouts": False, "predicted_risks": False},
        2,
    )

    assert defaults["failure"] == ["failed", "partial", "regressed", "timeout"]
    assert defaults["regression"] == ["regressed"]
    assert defaults["risk"] == ["risk"]
    assert disabled == {"failure": [], "regression": [], "risk": [], "control": []}


def test_ahe_rollout_caps_parallel_debuggers_at_five(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    checkout = workspace / "candidate-checkout"
    run_dir = workspace / "runs" / "gen-2"
    checkout.mkdir(parents=True)
    task_ids = [f"failed-{index}" for index in range(6)]
    artifacts = _write_artifacts(workspace, "1", task_ids)
    (workspace / "archive.jsonl").write_text(
        json.dumps({"genid": "1", **_scope(task_ids), "task_vector": _vector({task_id: [0, 0] for task_id in task_ids}), "evaluation_artifacts": artifacts})
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
        config=_rollout_config(task_ids, debugger={"command": "fake-debugger", "workers": 99}),
        rng=random.Random(0),
    )

    AHE_ROLLOUT.AheTraceAnalysisRollout().rollout(checkout, ctx)

    assert maximum == 5


def test_installed_rollout_imports_support_and_reads_copied_prompts(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    config = workspace_module.default_config("ahe-smoke", "installed-ahe")
    config["operators"]["rollout"] = {"variant": "ahe_trace_analysis"}
    monkeypatch.setattr(workspace_module, "default_config", lambda _recipe, _experiment: copy.deepcopy(config))
    workspace = tmp_path / "installed-ahe"
    workspace_module.init_workspace(workspace_module.InitOptions(workspace=workspace, recipe="ahe-smoke"))

    installed_rollout = workspace / "operators" / "rollout.py"
    code = (
        "import importlib.util\n"
        f"path = {str(installed_rollout)!r}\n"
        "spec = importlib.util.spec_from_file_location('installed_ahe_rollout', path)\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "print(module._read_prompt('ahe_debugger.md').splitlines()[0])\n"
        "print(module._read_prompt('ahe_debugger_overview.md').splitlines()[0])\n"
    )
    result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, check=False, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["# AHE Trace Debugger", "# AHE Trace Analysis Overview"]
    assert (workspace / "library" / "ahe_support.py").is_file()
    assert (workspace / "library" / "rollout" / "prompts" / "ahe_debugger.md").is_file()


def test_artifact_index_rejects_forged_hash(tmp_path: Path) -> None:
    index = tmp_path / "index.json"
    index.write_text('{"jobs_dir": "/tmp", "trials": []}\n')

    with pytest.raises(ValueError, match="sha256"):
        AHE_ROLLOUT._artifact_index(
            {"evaluation_artifacts": {"path": "index.json", "sha256": "0" * 64}},
            tmp_path,
        )


def test_verified_bytes_rehashes_exact_returned_bytes(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "trace.txt"
    authentic = b"authentic trace\n"
    artifact.write_bytes(b"forged after verification\n")
    reference = {"path": "trace.txt", "sha256": hashlib.sha256(authentic).hexdigest()}
    monkeypatch.setattr(AHE_ROLLOUT, "verify_relative_hash", lambda _root, _reference: artifact)

    with pytest.raises(ValueError, match="sha256"):
        AHE_ROLLOUT._verified_bytes(tmp_path, reference)


def test_task_artifacts_reject_forged_trace_hash(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs"
    trace = jobs / "trace.txt"
    trace.parent.mkdir()
    trace.write_text("forged trace\n")
    index = {
        "jobs_dir": str(jobs),
        "trials": [{"task_name": "task", "files": [{"path": "trace.txt", "sha256": "0" * 64}]}],
    }

    with pytest.raises(ValueError, match="sha256"):
        AHE_ROLLOUT._task_artifacts(index, "task")


def test_task_artifacts_reject_sealed_jobs_dir(tmp_path: Path) -> None:
    jobs = tmp_path / "sealed" / "jobs"
    trace = jobs / "trace.txt"
    trace.parent.mkdir(parents=True)
    trace.write_text("sealed trace\n")
    index = {
        "jobs_dir": str(jobs),
        "trials": [{"task_name": "task", "files": [{"path": "trace.txt", "sha256": _sha256(trace)}]}],
    }

    with pytest.raises(ValueError, match="sealed"):
        AHE_ROLLOUT._task_artifacts(index, "task")


def test_task_artifacts_reject_symlink_alias_to_sealed_path(tmp_path: Path, monkeypatch) -> None:
    jobs = tmp_path / "jobs"
    sealed = jobs / "sealed"
    trace = sealed / "trace.txt"
    trace.parent.mkdir(parents=True)
    trace.write_text("sealed trace\n")
    (jobs / "alias").symlink_to(sealed, target_is_directory=True)
    index = {
        "jobs_dir": str(jobs),
        "trials": [{"task_name": "task", "files": [{"path": "alias/trace.txt", "sha256": _sha256(trace)}]}],
    }
    verified_calls = 0

    def unexpected_verified_bytes(_root: Path, _reference: object):
        nonlocal verified_calls
        verified_calls += 1
        raise AssertionError("sealed evidence reached verification/read helper")

    monkeypatch.setattr(AHE_ROLLOUT, "_verified_bytes", unexpected_verified_bytes)

    with pytest.raises(ValueError, match="sealed"):
        AHE_ROLLOUT._task_artifacts(index, "task")
    assert verified_calls == 0


def test_task_artifacts_sanitize_secret_and_proxy_credentials_before_prompt(tmp_path: Path, monkeypatch) -> None:
    jobs = tmp_path / "jobs"
    trace = jobs / "trace.txt"
    trace.parent.mkdir()
    secret = "opaque-debugger-secret"
    proxy_url = "http://proxy-user:proxy-password@proxy.example:8118"
    trace.write_text(f"Useful failure phase: parser\nsecret={secret}\nproxy={proxy_url}\nsk-live-token-value\n")
    monkeypatch.setenv("EVOLVE_DEBUGGER_TOKEN", secret)
    index = {
        "jobs_dir": str(jobs),
        "trials": [{"task_name": "task", "files": [{"path": "trace.txt", "sha256": _sha256(trace)}]}],
    }

    evidence = AHE_ROLLOUT._task_artifacts(index, "task")

    assert "Useful failure phase: parser" in evidence[0][1]
    assert secret not in evidence[0][1]
    assert proxy_url not in evidence[0][1]
    assert "sk-live-token-value" not in evidence[0][1]
    assert "[REDACTED]" in evidence[0][1]


def test_rollout_rejects_innocuous_heldout_task_before_prompt_construction(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    checkout = workspace / "candidate-checkout"
    run_dir = workspace / "runs" / "gen-2"
    checkout.mkdir(parents=True)
    task_ids = ["train-task", "heldout-test-task"]
    artifacts = _write_artifacts(workspace, "1", task_ids)
    (workspace / "archive.jsonl").write_text(
        json.dumps(
            {
                "genid": "1",
                **_scope(task_ids),
                "task_vector": _vector({task_id: [0, 0] for task_id in task_ids}),
                "evaluation_artifacts": artifacts,
            }
        )
        + "\n"
    )
    monkeypatch.setattr(
        AHE_ROLLOUT,
        "_detail_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("heldout evidence reached prompt construction")),
    )
    ctx = OperatorContext(
        workspace=workspace,
        checkout=checkout,
        run_dir=run_dir,
        genid="2",
        parent="1",
        round=None,
        fan_out=1,
        config=_rollout_config(["train-task"]),
        rng=random.Random(0),
    )

    with pytest.raises(ValueError, match="training allowlist"):
        AHE_ROLLOUT.AheTraceAnalysisRollout().rollout(checkout, ctx)


def test_unsafe_task_id_uses_hashed_report_path(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    checkout = workspace / "candidate-checkout"
    run_dir = workspace / "runs" / "gen-2"
    checkout.mkdir(parents=True)
    task_id = "../escape"
    artifacts = _write_artifacts(workspace, "1", [task_id])
    (workspace / "archive.jsonl").write_text(
        json.dumps({"genid": "1", **_scope([task_id]), "task_vector": _vector({task_id: [0, 0]}), "evaluation_artifacts": artifacts}) + "\n"
    )

    monkeypatch.setattr(
        AHE_ROLLOUT,
        "run_meta_agent",
        lambda **_kwargs: SimpleNamespace(stdout="report\n"),
    )
    ctx = OperatorContext(
        workspace=workspace,
        checkout=checkout,
        run_dir=run_dir,
        genid="2",
        parent="1",
        round=None,
        fan_out=1,
        config=_rollout_config([task_id]),
        rng=random.Random(0),
    )

    result = AHE_ROLLOUT.AheTraceAnalysisRollout().rollout(checkout, ctx)

    detail_dir = (run_dir / "rollout" / "analysis" / "detail").resolve()
    reports = list(detail_dir.glob("*.md"))
    assert len(reports) == 1
    assert reports[0].resolve().parent == detail_dir
    assert reports[0].name == f"_task-{hashlib.sha256(task_id.encode()).hexdigest()}.md"
    assert not (run_dir / "rollout" / "analysis" / "escape.md").exists()
    assert f"rollout/analysis/detail/{reports[0].name}" in result.artifacts


def test_unsafe_and_safe_hash_like_task_ids_use_distinct_reports(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    checkout = workspace / "candidate-checkout"
    run_dir = workspace / "runs" / "gen-2"
    checkout.mkdir(parents=True)
    unsafe_id = "../escape"
    digest = hashlib.sha256(unsafe_id.encode()).hexdigest()
    safe_id = f"task-{digest}"
    artifacts = _write_artifacts(workspace, "1", [unsafe_id, safe_id])
    (workspace / "archive.jsonl").write_text(
        json.dumps(
            {
                "genid": "1",
                **_scope([unsafe_id, safe_id]),
                "task_vector": _vector({unsafe_id: [0, 0], safe_id: [0, 0]}),
                "evaluation_artifacts": artifacts,
            }
        )
        + "\n"
    )
    monkeypatch.setattr(AHE_ROLLOUT, "run_meta_agent", lambda **_kwargs: SimpleNamespace(stdout="report\n"))
    ctx = OperatorContext(
        workspace=workspace,
        checkout=checkout,
        run_dir=run_dir,
        genid="2",
        parent="1",
        round=None,
        fan_out=1,
        config=_rollout_config([unsafe_id, safe_id]),
        rng=random.Random(0),
    )

    result = AHE_ROLLOUT.AheTraceAnalysisRollout().rollout(checkout, ctx)

    detail_dir = run_dir / "rollout" / "analysis" / "detail"
    expected = {f"_task-{digest}.md", f"{safe_id}.md"}
    assert {path.name for path in detail_dir.glob("*.md")} == expected
    assert {Path(path).name for path in result.artifacts if path.startswith("rollout/analysis/detail/")} == expected


def test_manifest_rehashes_exact_returned_bytes(tmp_path: Path, monkeypatch) -> None:
    manifest = tmp_path / "manifest.json"
    authentic = b'{"changes": []}\n'
    manifest.write_bytes(b'{"changes": [{"id": "forged"}]}\n')
    parent = {
        "ahe_manifest_path": "manifest.json",
        "ahe_manifest_sha256": hashlib.sha256(authentic).hexdigest(),
    }
    monkeypatch.setattr(AHE_ROLLOUT, "verify_relative_hash", lambda _root, _reference: manifest)

    with pytest.raises(ValueError, match="sha256"):
        AHE_ROLLOUT._manifest(parent, tmp_path)


def test_terminal_debugger_failure_records_attempts(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    checkout = workspace / "candidate-checkout"
    run_dir = workspace / "runs" / "gen-2"
    checkout.mkdir(parents=True)
    artifacts = _write_artifacts(workspace, "1", ["failed-task"])
    (workspace / "archive.jsonl").write_text(
        json.dumps({"genid": "1", **_scope(["failed-task"]), "task_vector": _vector({"failed-task": [0, 0]}), "evaluation_artifacts": artifacts}) + "\n"
    )
    attempts = 0

    def fake_run_meta_agent(*, env_overrides: dict, **_kwargs):
        nonlocal attempts
        if env_overrides["EVOLVE_SOURCE_AGENT_ROLE"] == "debugger":
            attempts += 1
            raise RuntimeError("debugger failed")
        return SimpleNamespace(stdout="overview\n")

    monkeypatch.setattr(AHE_ROLLOUT, "run_meta_agent", fake_run_meta_agent)
    ctx = OperatorContext(
        workspace=workspace,
        checkout=checkout,
        run_dir=run_dir,
        genid="2",
        parent="1",
        round=None,
        fan_out=1,
        config=_rollout_config(["failed-task"], debugger={"command": "fake-debugger", "attempts": 2}),
        rng=random.Random(0),
    )

    with pytest.raises(ValueError, match="no successful AHE detail report"):
        AHE_ROLLOUT.AheTraceAnalysisRollout().rollout(checkout, ctx)

    failures = json.loads((run_dir / "rollout" / "analysis" / "failures.json").read_text())
    assert attempts == 2
    assert failures == {"failures": [{"attempts": 2, "error": "debugger failed", "task_id": "failed-task"}]}
