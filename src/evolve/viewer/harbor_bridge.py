from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from urllib.parse import quote

from harbor.viewer.scanner import JobScanner
from harbor.viewer.trial_utils import agent_name_from_result, trial_summary_from_config

from .models import HarborTrialLink, JobRootReference

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_.-]+")


@dataclass(frozen=True)
class HarborFederation:
    root: Path
    job_names: dict[tuple[Path, str], str]
    trial_links: dict[tuple[str, str, str, int], HarborTrialLink]


class HarborBridge:
    """Expose referenced Harbor jobs through a disposable symlink directory."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self._tempdir: tempfile.TemporaryDirectory[str] | None = None
        self.root: Path | None = None

    def __enter__(self) -> HarborBridge:
        if self._tempdir is None:
            self._tempdir = tempfile.TemporaryDirectory(prefix="evolve-view-harbor-")
            self.root = Path(self._tempdir.name)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._tempdir is not None:
            self._tempdir.cleanup()
        self._tempdir = None
        self.root = None

    def refresh(
        self,
        job_roots: Iterable[JobRootReference],
        *,
        canonical_tasks: Mapping[tuple[str, str], Iterable[str]] | None = None,
    ) -> HarborFederation:
        root = self._require_root()
        references = tuple(job_roots)
        desired = _federated_jobs(references)
        for name, target in desired.values():
            temporary = root / f".{name}.next"
            temporary.unlink(missing_ok=True)
            temporary.symlink_to(target, target_is_directory=True)
            os.replace(temporary, root / name)
        expected = {name for name, _target in desired.values()}
        for entry in root.iterdir():
            if entry.name not in expected:
                entry.unlink(missing_ok=True)

        job_names = {key: value[0] for key, value in desired.items()}
        reference_by_job = {
            name: reference
            for reference in references
            for child in _job_children(reference.path)
            if (name := job_names.get((reference.path.resolve(), child.name))) is not None
        }
        return HarborFederation(
            root=root,
            job_names=job_names,
            trial_links=_trial_links(root, reference_by_job, canonical_tasks or {}),
        )

    def _require_root(self) -> Path:
        if self.root is None:
            raise RuntimeError("HarborBridge must be entered before refresh")
        return self.root


def _federated_jobs(
    references: Iterable[JobRootReference],
) -> dict[tuple[Path, str], tuple[str, Path]]:
    jobs: dict[tuple[Path, str], tuple[str, Path]] = {}
    for reference in references:
        source_root = reference.path.resolve()
        for child in _job_children(source_root):
            digest = hashlib.sha256(str(child.resolve()).encode()).hexdigest()[:10]
            stem = _SAFE_NAME.sub("-", child.name).strip("-.") or "job"
            jobs[(source_root, child.name)] = (f"{stem}-{digest}", child.resolve())
    return jobs


def _job_children(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        return ()
    return tuple(
        sorted(
            (
                child
                for child in root.iterdir()
                if child.is_dir()
                and ((child / "config.json").is_file() or (child / "result.json").is_file())
            ),
            key=lambda child: child.name,
        )
    )


def _trial_links(
    root: Path,
    reference_by_job: Mapping[str, JobRootReference],
    canonical_tasks: Mapping[tuple[str, str], Iterable[str]],
) -> dict[tuple[str, str, str, int], HarborTrialLink]:
    scanner = JobScanner(root)
    links: dict[tuple[str, str, str, int], HarborTrialLink] = {}
    for job_name, reference in sorted(reference_by_job.items()):
        key = (reference.generation, reference.purpose)
        candidates = tuple(str(task) for task in canonical_tasks.get(key, ()))
        for repetition, trial_name in enumerate(scanner.list_trials(job_name)):
            trial = _trial_evidence(scanner, job_name, trial_name)
            if trial is None:
                continue
            task_name, source, agent, provider, model, reward, duration_ms = trial
            canonical = _canonical_task(task_name, candidates)
            if canonical is None:
                continue
            parts = [quote(part or "unknown", safe="") for part in (job_name, source, agent, provider, model, task_name, trial_name)]
            url = f"/jobs/{parts[0]}/tasks/{'/'.join(parts[1:6])}/trials/{parts[6]}"
            links[(reference.generation, reference.purpose, canonical, repetition)] = HarborTrialLink(
                url=url,
                reward=reward,
                duration_ms=duration_ms,
            )
    return links


def _trial_evidence(
    scanner: JobScanner, job_name: str, trial_name: str
) -> tuple[str, str | None, str | None, str | None, str | None, float | None, float | None] | None:
    result = scanner.get_trial_result(job_name, trial_name)
    if result is not None:
        model = result.agent_info.model_info
        reward = (
            result.verifier_result.rewards.get("reward")
            if result.verifier_result and result.verifier_result.rewards
            else None
        )
        duration = (
            (result.finished_at - result.started_at).total_seconds() * 1000
            if result.finished_at is not None and result.started_at is not None
            else None
        )
        return (
            result.task_name,
            result.source,
            agent_name_from_result(result),
            model.provider if model else None,
            model.name if model else None,
            float(reward) if isinstance(reward, (int, float)) else None,
            duration,
        )
    config = scanner.get_trial_config(job_name, trial_name)
    if config is None:
        return None
    summary = trial_summary_from_config(trial_name, config)
    return (
        summary.task_name,
        summary.source,
        summary.agent_name,
        summary.model_provider,
        summary.model_name,
        summary.reward,
        None,
    )


def _canonical_task(harbor_task: str, candidates: tuple[str, ...]) -> str | None:
    if not candidates:
        return harbor_task
    if harbor_task in candidates:
        return harbor_task
    matches = [candidate for candidate in candidates if candidate.endswith(f"__{harbor_task}")]
    return matches[0] if len(matches) == 1 else None
