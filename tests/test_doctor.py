from __future__ import annotations

import json
from pathlib import Path

import evolve.doctor as doctor
from evolve.execution_runtime import ExecutionRuntimeProbeReport, RuntimeCheck


def _stub_runtime(monkeypatch, captured: list[object]) -> None:
    def resolve(config):
        captured.append(config)
        return object()

    def probe(_runtime, *, workspace):
        return ExecutionRuntimeProbeReport(
            receipt={"fingerprint": "runtime"},
            checks=(RuntimeCheck("runtime", "pass", str(workspace)),),
        )

    monkeypatch.setattr(doctor, "resolve_execution_runtime", resolve)
    monkeypatch.setattr(doctor, "probe_execution_runtime", probe)
    monkeypatch.setattr(doctor, "_codex_checks", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(doctor, "_plugin_checks", lambda _root: [])


def test_local_doctor_is_lightweight_and_persists_receipt(tmp_path: Path, monkeypatch) -> None:
    captured: list[object] = []
    _stub_runtime(monkeypatch, captured)

    report = doctor.run_doctor(tmp_path, profile="local")

    config = captured[0]
    assert config.backend == "local"
    assert config.minimum_free_gib == 1
    assert report.healthy
    assert json.loads(report.report_path.read_text())["healthy"] is True


def test_experiment_doctor_uses_declared_runtime_policy(tmp_path: Path, monkeypatch) -> None:
    captured: list[object] = []
    _stub_runtime(monkeypatch, captured)
    (tmp_path / "evolve.yaml").write_text(
        "experiment: {id: test}\n"
        "target: {}\n"
        "surface: {}\n"
        "operators: {}\n"
        "evaluator: {}\n"
        "execution_runtime: {backend: docker, minimum_free_gib: 80}\n"
    )
    monkeypatch.setattr(doctor, "_experiment_checks", lambda *_args, **_kwargs: [])

    report = doctor.run_doctor(tmp_path, profile="experiment")

    config = captured[0]
    assert config.backend == "docker"
    assert config.minimum_free_gib == 80
    assert report.healthy
