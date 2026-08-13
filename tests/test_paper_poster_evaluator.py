from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / "evals" / "skills" / "make-paper-poster" / "task_assets" / "evaluate.py"
RECIPE = ROOT / "evals" / "skills" / "make-paper-poster" / "recipe" / "evolve.yaml"
RUBRIC = EVALUATOR.parents[1] / "rubric.json"
SCHEMA = EVALUATOR.parent / "judge_schema.json"


def _load_evaluator():
    spec = importlib.util.spec_from_file_location("paper_poster_evaluator", EVALUATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_poster_recipe_uses_codex_defaults_under_outer_agent_control() -> None:
    recipe = yaml.safe_load(RECIPE.read_text())

    assert "model" not in recipe["evaluator"]
    assert "model" not in recipe["operators"]["mutate"]


def test_renderer_uses_injected_local_runtime_and_preserves_rsvg_fallback(monkeypatch, tmp_path: Path) -> None:
    module = _load_evaluator()
    module.POSTER = tmp_path / "poster.svg"
    module.PNG = tmp_path / "poster.png"
    module.POSTER.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        calls.append(command)
        receipt = {"output": str(module.PNG), "engine": "resvg", "runtime_digest": "sha256:test"}
        return subprocess.CompletedProcess(command, 0, json.dumps(receipt), "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        module,
        "validate_renderer_runtime",
        lambda _: {"runtime_digest": "sha256:test"},
    )
    monkeypatch.setenv("EVOLVE_SVG_RENDERER", "/runtime/evolve-render-svg")
    assert module.render()["engine"] == "resvg"
    assert calls[-1] == [
        "/runtime/evolve-render-svg",
        str(module.POSTER),
        "--width",
        "1600",
        "--output",
        str(module.PNG),
    ]

    monkeypatch.delenv("EVOLVE_SVG_RENDERER")
    assert module.render()["engine"] == "rsvg-convert"
    assert calls[-1] == [
        "rsvg-convert",
        "--width",
        "1600",
        "--output",
        str(module.PNG),
        str(module.POSTER),
    ]


def test_visual_judge_makes_one_supported_model_call_and_returns_prose(monkeypatch, tmp_path: Path) -> None:
    module = _load_evaluator()
    workdir = tmp_path / "work"
    log_dir = tmp_path / "logs"
    workdir.mkdir()
    log_dir.mkdir()
    module.WORKDIR = workdir
    module.LOG_DIR = log_dir
    module.PAPER = workdir / "paper.pdf"
    module.PAPER_TEXT = workdir / "paper.txt"
    module.PNG = workdir / "poster.png"
    module.RUBRIC = RUBRIC
    module.SCHEMA = SCHEMA
    monkeypatch.delenv("PAPER_POSTER_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("EVOLVE_HARBOR_MODEL", raising=False)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        calls.append(command)
        if command[0] == "pdftotext":
            module.PAPER_TEXT.write_text("paper text")
        elif command[0] == "codex":
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(json.dumps({"feedback": "The visual story is clear; tighten the typography."}))
        else:
            raise AssertionError(f"unexpected subprocess: {command}")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module.run_judge({"svg_geometry_check": {"exit_code": 0}}) == {
        "feedback": "The visual story is clear; tighten the typography."
    }
    judge_calls = [command for command in calls if command[0] == "codex"]
    assert len(judge_calls) == 1
    assert "--model" not in judge_calls[0]
    assert judge_calls[0][judge_calls[0].index("--image") + 1] == str(module.PNG)


def test_visual_judge_inherits_rollout_model_but_allows_specific_override(monkeypatch, tmp_path: Path) -> None:
    module = _load_evaluator()
    workdir = tmp_path / "work"
    log_dir = tmp_path / "logs"
    workdir.mkdir()
    log_dir.mkdir()
    module.WORKDIR = workdir
    module.LOG_DIR = log_dir
    module.PAPER = workdir / "paper.pdf"
    module.PAPER_TEXT = workdir / "paper.txt"
    module.PNG = workdir / "poster.png"
    module.RUBRIC = RUBRIC
    module.SCHEMA = SCHEMA
    monkeypatch.setenv("EVOLVE_HARBOR_MODEL", "gpt-rollout")
    monkeypatch.setenv("PAPER_POSTER_JUDGE_MODEL", "gpt-judge")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        calls.append(command)
        if command[0] == "pdftotext":
            module.PAPER_TEXT.write_text("paper text")
        else:
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(json.dumps({"feedback": "Focused visual feedback."}))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    monkeypatch.delenv("PAPER_POSTER_JUDGE_MODEL")
    assert module.run_judge({}) == {"feedback": "Focused visual feedback."}
    judge_calls = [command for command in calls if command[0] == "codex"]
    assert judge_calls[-1][judge_calls[-1].index("--model") + 1] == "gpt-rollout"

    monkeypatch.setenv("PAPER_POSTER_JUDGE_MODEL", "gpt-judge")
    assert module.run_judge({}) == {"feedback": "Focused visual feedback."}
    judge_calls = [command for command in calls if command[0] == "codex"]
    assert judge_calls[-1][judge_calls[-1].index("--model") + 1] == "gpt-judge"


def test_successful_evaluation_uses_completion_reward_and_no_quality_score(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HARBOR_WORKDIR", str(tmp_path))
    module = _load_evaluator()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    module.LOG_DIR = log_dir
    monkeypatch.setattr(module, "static_check", lambda: ([], {"svg_bytes": 123}))
    monkeypatch.setattr(module, "render", lambda: None)
    monkeypatch.setattr(
        module,
        "svg_geometry_check",
        lambda: {
            "exit_code": 0,
            "result": {"valid": True, "summary": {"textOverflow": 0, "nodeOverflow": 0}},
        },
    )
    monkeypatch.setattr(module, "run_judge", lambda _: {"feedback": "Improve the focal point."})

    assert module.main() == 0
    payload = json.loads((log_dir / "evaluation.json").read_text())
    assert payload["reward"] == 1.0
    assert payload["feedback"] == "Improve the focal point."
    assert "score" not in payload


def test_geometry_checker_failures_are_evaluator_infrastructure_errors(monkeypatch) -> None:
    module = _load_evaluator()

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "not-json", ""),
    )
    with pytest.raises(RuntimeError, match="invalid JSON"):
        module.svg_geometry_check()

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "{}", ""),
    )
    with pytest.raises(RuntimeError, match="invalid result schema"):
        module.svg_geometry_check()

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 2, "{}", "checker crashed"),
    )
    with pytest.raises(RuntimeError, match="failed with exit code 2"):
        module.svg_geometry_check()

    def timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        raise subprocess.TimeoutExpired("svg-check", 180)

    monkeypatch.setattr(module.subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        module.svg_geometry_check()


def test_text_overflow_is_a_deterministic_geometry_hard_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HARBOR_WORKDIR", str(tmp_path))
    module = _load_evaluator()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    module.LOG_DIR = log_dir
    monkeypatch.setattr(module, "static_check", lambda: ([], {"svg_bytes": 123}))
    monkeypatch.setattr(module, "render", lambda: None)
    monkeypatch.setattr(
        module,
        "svg_geometry_check",
        lambda: {"exit_code": 0, "result": {"summary": {"textOverflow": 3}}},
    )
    monkeypatch.setattr(module, "run_judge", lambda _: {"feedback": "Several labels are visibly clipped."})

    assert module.main() == 0
    payload = json.loads((log_dir / "evaluation.json").read_text())
    assert payload["reward"] == 0.0
    assert payload["hard_failures"] == ["geometry_integrity: 3 text elements overflow the SVG viewBox"]
    assert payload["feedback"] == "Several labels are visibly clipped."


def test_node_overflow_is_a_deterministic_geometry_hard_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HARBOR_WORKDIR", str(tmp_path))
    module = _load_evaluator()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    module.LOG_DIR = log_dir
    monkeypatch.setattr(module, "static_check", lambda: ([], {"svg_bytes": 123}))
    monkeypatch.setattr(module, "render", lambda: None)
    monkeypatch.setattr(
        module,
        "svg_geometry_check",
        lambda: {"exit_code": 0, "result": {"valid": False, "summary": {"nodeOverflow": 2}}},
    )
    monkeypatch.setattr(module, "run_judge", lambda _: {"feedback": "Two decorative nodes leave the canvas."})

    assert module.main() == 0
    payload = json.loads((log_dir / "evaluation.json").read_text())
    assert payload["reward"] == 0.0
    assert payload["hard_failures"] == ["geometry_integrity: 2 non-text elements overflow the SVG viewBox"]
