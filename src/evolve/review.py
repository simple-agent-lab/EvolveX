from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .git import add_worktree, git_stdout, remove_worktree
from .runtime import run_owned

_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_SEVERITIES = {"P0", "P1", "P2"}
_CONFIDENCE = {"high", "medium", "low"}
_VERDICTS = {"ready", "needs_changes", "discuss"}


class ReviewFormatError(ValueError):
    pass


@dataclass(frozen=True)
class ReviewTask:
    name: str
    instruction: str
    rubrics: tuple[str, ...]
    max_findings: int = 10
    schema_version: int = 1

    @classmethod
    def load(cls, path: Path | str) -> ReviewTask:
        source = Path(path)
        try:
            data = tomllib.loads(source.read_text())
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ReviewFormatError(f"invalid review task {source}: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewTask:
        task = cls(
            name=_required_text(data, "name"),
            instruction=_required_text(data, "instruction"),
            rubrics=tuple(_required_text_list(data, "rubrics")),
            max_findings=_required_int(data, "max_findings", default=10),
            schema_version=_required_int(data, "schema_version", default=1),
        )
        task.validate()
        return task

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "instruction": self.instruction,
            "rubrics": list(self.rubrics),
            "max_findings": self.max_findings,
        }

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ReviewFormatError(f"unsupported review task schema: {self.schema_version}")
        if not _NAME.fullmatch(self.name):
            raise ReviewFormatError(f"invalid review task name: {self.name!r}")
        if len(set(self.rubrics)) != len(self.rubrics):
            raise ReviewFormatError("review task rubrics must be unique")
        if not 1 <= self.max_findings <= 50:
            raise ReviewFormatError("max_findings must be between 1 and 50")


@dataclass(frozen=True)
class ReviewEvidence:
    path: str
    detail: str
    line: int | None = None


@dataclass(frozen=True)
class ReviewFinding:
    severity: str
    category: str
    title: str
    evidence: tuple[ReviewEvidence, ...]
    impact: str
    smallest_fix: str
    confidence: str


@dataclass(frozen=True)
class ReviewReport:
    verdict: str
    summary: str
    findings: tuple[ReviewFinding, ...]
    questions: tuple[str, ...]
    strengths: tuple[str, ...]
    schema_version: int = 1

    @classmethod
    def load(cls, path: Path | str, task: ReviewTask) -> ReviewReport:
        source = Path(path)
        try:
            data = json.loads(source.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ReviewFormatError(f"invalid review report {source}: {exc}") from exc
        if not isinstance(data, dict):
            raise ReviewFormatError("review report must be a JSON object")
        findings_raw = data.get("findings")
        if not isinstance(findings_raw, list):
            raise ReviewFormatError("review report findings must be a list")
        findings = tuple(_finding(value, task) for value in findings_raw)
        if len(findings) > task.max_findings:
            raise ReviewFormatError(f"review report exceeds max_findings={task.max_findings}")
        report = cls(
            verdict=_required_text(data, "verdict"),
            summary=_required_text(data, "summary"),
            findings=findings,
            questions=tuple(_text_list(data, "questions")),
            strengths=tuple(_text_list(data, "strengths")),
            schema_version=_required_int(data, "schema_version", default=1),
        )
        if report.schema_version != 1:
            raise ReviewFormatError(f"unsupported review report schema: {report.schema_version}")
        if report.verdict not in _VERDICTS:
            raise ReviewFormatError(f"invalid review verdict: {report.verdict!r}")
        return report


@dataclass(frozen=True)
class ReviewRun:
    run_dir: Path
    task: ReviewTask
    base_commit: str
    head_commit: str
    report_path: Path
    trajectory_path: Path
    result_path: Path
    wall_s: float
    report: ReviewReport


def default_task_path() -> Path:
    source = Path(__file__).resolve().parents[2] / "review_tasks/framework-quality.toml"
    installed = Path(__file__).resolve().parent / "review_tasks/framework-quality.toml"
    return source if source.is_file() else installed


def run_review(
    repository: Path | str,
    *,
    task: ReviewTask,
    base_ref: str,
    head_ref: str = "HEAD",
    model: str = "gpt-5.4",
    reasoning_effort: str = "medium",
    runs_dir: Path | str | None = None,
) -> ReviewRun:
    repo = Path(repository).resolve()
    git_stdout(repo, "rev-parse", "--show-toplevel")
    base_commit = git_stdout(repo, "rev-parse", f"{base_ref}^{{commit}}")
    head_commit = git_stdout(repo, "rev-parse", f"{head_ref}^{{commit}}")
    run_dir = _new_run_dir(repo, task.name, runs_dir)
    jobs_dir = run_dir / "jobs"
    harbor_task = run_dir / "harbor-task"
    _write_harbor_task(harbor_task, task, base_commit, head_commit)
    (run_dir / "run.json").write_text(
        json.dumps(
            _run_manifest(task, repo, base_commit, head_commit, model, reasoning_effort), indent=2, sort_keys=True
        )
        + "\n"
    )

    with tempfile.TemporaryDirectory(prefix="evolve-review-") as temporary:
        checkout = Path(temporary) / "checkout"
        add_worktree(repo, checkout, head_commit)
        try:
            command = _harbor_command(harbor_task, jobs_dir, checkout, task, model, reasoning_effort)
            env = dict(os.environ)
            env.setdefault("CODEX_FORCE_AUTH_JSON", "1")
            result = run_owned(command, cwd=repo, env=env)
        finally:
            remove_worktree(repo, checkout)

    (run_dir / "harbor.stdout").write_text(result.stdout)
    (run_dir / "harbor.stderr").write_text(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"review agent failed with exit {result.returncode}; artifacts: {run_dir}")

    return collect_review_run(run_dir, wall_s=result.wall_s)


def collect_review_run(run_dir: Path | str, *, wall_s: float | None = None) -> ReviewRun:
    root = Path(run_dir).resolve()
    manifest_path = root / "run.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewFormatError(f"invalid review run manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ReviewFormatError("review run manifest must be a JSON object")
    data = cast(dict[str, Any], manifest)
    task_data = data.get("task")
    if not isinstance(task_data, dict):
        raise ReviewFormatError("review run manifest is missing its task snapshot")
    task = ReviewTask.from_dict(cast(dict[str, Any], task_data))
    result_path = _trial_result(root / "jobs")
    trajectory_path = result_path.parent / "agent/trajectory.json"
    report_path = result_path.parent / "agent/review-report.json"
    for path, label in ((trajectory_path, "ATIF trajectory"), (report_path, "review report")):
        if not path.is_file():
            raise RuntimeError(f"missing {label}: {path}")
    _validate_trajectory(trajectory_path)
    report = ReviewReport.load(report_path, task)
    resolved_wall = wall_s if wall_s is not None else _result_wall_s(result_path)
    data.update(
        {
            "wall_s": round(resolved_wall, 6),
            "report": report_path.relative_to(root).as_posix(),
            "trajectory": trajectory_path.relative_to(root).as_posix(),
            "result": result_path.relative_to(root).as_posix(),
        }
    )
    manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return ReviewRun(
        root,
        task,
        _required_text(data, "base_commit"),
        _required_text(data, "head_commit"),
        report_path,
        trajectory_path,
        result_path,
        resolved_wall,
        report,
    )


def _new_run_dir(repo: Path, task_name: str, configured: Path | str | None) -> Path:
    parent = Path(configured).resolve() if configured else repo / "runs/reviews"
    stamp = datetime.now(UTC).strftime("%Y-%m-%d__%H-%M-%S-%f")
    path = parent / f"{stamp}__{task_name}"
    path.mkdir(parents=True)
    return path


def _write_harbor_task(path: Path, task: ReviewTask, base_commit: str, head_commit: str) -> None:
    path.mkdir(parents=True)
    (path / "environment").mkdir()
    (path / "task.toml").write_text(
        'version = "1.0"\n\n[agent]\ntimeout_sec = 900.0\n\n[environment]\nworkdir = "/app"\n'
    )
    rubrics = ", ".join(task.rubrics)
    (path / "instruction.md").write_text(
        f"{task.instruction.strip()}\n\n"
        f"Review exactly `{base_commit}..{head_commit}`. The checkout is pinned at the head commit.\n"
        f"Enabled rubric categories: {rubrics}. Return at most {task.max_findings} actionable findings.\n"
        "Do not edit the repository. Every finding requires a severity (P0, P1, or P2), enabled category, "
        "title, non-empty evidence with path/detail and optional line, impact, smallest_fix, and confidence "
        "(high, medium, or low). Write a JSON object with schema_version=1, verdict "
        "(ready, needs_changes, or discuss), summary, findings, questions, and strengths to "
        "`$HARBOR_LOGS_DIR/agent/review-report.json`, then return a concise human-readable review.\n"
    )


def _harbor_command(
    task_dir: Path, jobs_dir: Path, checkout: Path, task: ReviewTask, model: str, reasoning_effort: str
) -> list[str]:
    return [
        _harbor_executable(),
        "run",
        "--path",
        str(task_dir),
        "--jobs-dir",
        str(jobs_dir),
        "--job-name",
        f"review-{task.name}",
        "--agent",
        "codex",
        "--model",
        model,
        "--agent-kwarg",
        f"reasoning_effort={reasoning_effort}",
        "--agent-env",
        "HOME=/tmp/evolve-review-home",
        "--env",
        "evolve.harbor_local:LocalEnvironment",
        "--environment-kwarg",
        f'workspace_dir="{checkout}"',
        "--disable-verification",
        "--n-concurrent",
        "1",
        "--n-attempts",
        "1",
        "--yes",
    ]


def _harbor_executable() -> str:
    candidate = shutil.which("harbor") or str(Path(sys.executable).with_name("harbor"))
    if not Path(candidate).is_file():
        raise RuntimeError("harbor executable is missing from the evolve environment")
    return candidate


def _trial_result(root: Path) -> Path:
    matches: list[Path] = []
    for path in root.rglob("result.json"):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("task_name") and data.get("trial_name"):
            matches.append(path)
    if len(matches) != 1:
        raise RuntimeError(f"expected one trial result under {root}, found {len(matches)}")
    return matches[0]


def _validate_trajectory(path: Path) -> None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewFormatError(f"invalid ATIF trajectory {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReviewFormatError("ATIF trajectory must be a JSON object")
    schema_version = value.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.startswith("ATIF-v"):
        raise ReviewFormatError("trajectory schema_version must identify ATIF")
    if not isinstance(value.get("session_id"), str) or not value["session_id"].strip():
        raise ReviewFormatError("ATIF trajectory requires a session_id")
    if not isinstance(value.get("steps"), list):
        raise ReviewFormatError("ATIF trajectory steps must be a list")


def _run_manifest(
    task: ReviewTask, repo: Path, base: str, head: str, model: str, reasoning_effort: str
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task": task.to_dict(),
        "repository": str(repo),
        "base_commit": base,
        "head_commit": head,
        "model": model,
        "reasoning_effort": reasoning_effort,
    }


def _result_wall_s(path: Path) -> float:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ReviewFormatError("trial result must be a JSON object")
    started = datetime.fromisoformat(_required_text(data, "started_at").replace("Z", "+00:00"))
    finished = datetime.fromisoformat(_required_text(data, "finished_at").replace("Z", "+00:00"))
    return max(0.0, (finished - started).total_seconds())


def _finding(value: object, task: ReviewTask) -> ReviewFinding:
    if not isinstance(value, dict):
        raise ReviewFormatError("each review finding must be an object")
    data = cast(dict[str, Any], value)
    severity = _required_text(data, "severity")
    category = _required_text(data, "category")
    confidence = _required_text(data, "confidence")
    if severity not in _SEVERITIES:
        raise ReviewFormatError(f"invalid finding severity: {severity!r}")
    if category not in task.rubrics:
        raise ReviewFormatError(f"finding category is not enabled by the task: {category!r}")
    if confidence not in _CONFIDENCE:
        raise ReviewFormatError(f"invalid finding confidence: {confidence!r}")
    evidence_raw = data.get("evidence")
    if not isinstance(evidence_raw, list) or not evidence_raw:
        raise ReviewFormatError("each finding requires evidence")
    evidence = tuple(_evidence(item) for item in evidence_raw)
    return ReviewFinding(
        severity,
        category,
        _required_text(data, "title"),
        evidence,
        _required_text(data, "impact"),
        _required_text(data, "smallest_fix"),
        confidence,
    )


def _evidence(value: object) -> ReviewEvidence:
    if not isinstance(value, dict):
        raise ReviewFormatError("finding evidence must be an object")
    data = cast(dict[str, Any], value)
    line = data.get("line")
    if line is not None and (isinstance(line, bool) or not isinstance(line, int) or line < 1):
        raise ReviewFormatError("evidence line must be a positive integer")
    return ReviewEvidence(_required_text(data, "path"), _required_text(data, "detail"), line)


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReviewFormatError(f"{key} must be non-empty text")
    return value.strip()


def _text_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ReviewFormatError(f"{key} must be a list of non-empty strings")
    return [item.strip() for item in value]


def _required_text_list(data: dict[str, Any], key: str) -> list[str]:
    values = _text_list(data, key)
    if not values:
        raise ReviewFormatError(f"{key} must not be empty")
    return values


def _required_int(data: dict[str, Any], key: str, *, default: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReviewFormatError(f"{key} must be an integer")
    return value
