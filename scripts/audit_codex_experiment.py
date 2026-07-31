#!/usr/bin/env python3
"""Deterministically audit prepared Codex benchmark workspaces and smoke runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml

_CODEX_AGENT = "target.agent:HarborAgent"
_CODEX_MODEL = "gpt-5.4"
_PRIVATE_EVIDENCE_DIRS = frozenset({"rollout", "trace", "trace_analyzer", "feedback"})
_IMPLICIT_SURFACE_EXCLUDES = ("evaluator/**", "archive.jsonl", ".evolve/**", "evolve")


def _base_report(workspace: Path, mode: str) -> dict[str, object]:
    resolved = workspace.expanduser().resolve()
    return {
        "ok": False,
        "errors": [],
        "experiment": {
            "id": resolved.name,
            "mode": mode,
            "workspace": str(resolved),
            "config_path": str(resolved / "evolve.yaml"),
        },
        "tasks": {
            "manifest_path": str(resolved / "evaluator" / "splits.json"),
            "train_file": str(resolved / "evaluator" / "tasks" / "train.txt"),
            "sealed_file": str(resolved / "evaluator" / "tasks" / "sealed.txt"),
            "train_names": [],
            "train_count": 0,
            "gate_count": 0,
            "sealed_count": 0,
        },
        "lineage": {
            "through_generation": None,
            "generations": [],
            "complete_evaluations": 0,
            "harbor_config_count": 0,
            "surface_violations": [],
            "privacy_leaks": [],
        },
        "reasoning": {"reasoning_effort": None},
        "anchor": {"final": None, "every_rounds": None},
    }


def _errors(report: dict[str, object]) -> list[str]:
    errors = report["errors"]
    assert isinstance(errors, list)
    return errors


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_yaml_mapping(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"missing {label}: {path}")
        return {}
    try:
        value = yaml.safe_load(path.read_text())
    except (OSError, UnicodeError, yaml.YAMLError):
        errors.append(f"could not parse {label}: {path}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label} must contain a mapping: {path}")
        return {}
    return value


def _load_json_mapping(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"missing {label}: {path}")
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append(f"could not parse {label}: {path}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label} must contain a mapping: {path}")
        return {}
    return value


def _load_lines(path: Path, errors: list[str], label: str) -> list[str]:
    if not path.is_file():
        errors.append(f"missing {label}: {path}")
        return []
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeError):
        errors.append(f"could not read {label}: {path}")
        return []
    if any(not line for line in lines):
        errors.append(f"{label} contains an empty task name: {path}")
    return lines


def _load_key_values(path: Path, errors: list[str], label: str) -> dict[str, str]:
    if not path.is_file():
        errors.append(f"missing {label}: {path}")
        return {}
    values: dict[str, str] = {}
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeError):
        errors.append(f"could not read {label}: {path}")
        return {}
    for number, line in enumerate(lines, 1):
        key, separator, value = line.partition("=")
        if not separator or not key:
            errors.append(f"{label} has an invalid entry on line {number}: {path}")
            continue
        if key in values:
            errors.append(f"{label} repeats key {key}: {path}")
            continue
        values[key] = value
    return values


def _string_tasks(tasks: dict[str, Any], split: str, errors: list[str]) -> list[str]:
    value = tasks.get(split)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        errors.append(f"evaluator/splits.json tasks.{split} must be a list of non-empty strings")
        return []
    return list(value)


def _expect_equal(errors: list[str], actual: object, expected: object, label: str) -> None:
    if actual != expected:
        errors.append(f"{label} must be {expected!r}")


def _audit_prepared_for_anchor(workspace: Path, expected_anchor: str) -> dict[str, object]:
    workspace = workspace.expanduser().resolve()
    report = _base_report(workspace, "prepared")
    errors = _errors(report)
    if not workspace.is_dir():
        errors.append(f"workspace is not a directory: {workspace}")
        return report

    config = _load_yaml_mapping(workspace / "evolve.yaml", errors, "evolve.yaml")
    experiment = _mapping(config.get("experiment"))
    target = _mapping(config.get("target"))
    surface = _mapping(config.get("surface"))
    operators = _mapping(config.get("operators"))
    meta_agent = _mapping(operators.get("meta_agent"))
    evaluator = _mapping(config.get("evaluator"))

    experiment_report = _mapping(report["experiment"])
    if isinstance(experiment.get("id"), str) and experiment["id"]:
        experiment_report["id"] = experiment["id"]

    _expect_equal(errors, target.get("seed"), "builtin-codex", "target.seed")
    _expect_equal(errors, evaluator.get("engine"), "harbor", "evaluator.engine")
    _expect_equal(errors, evaluator.get("agent"), _CODEX_AGENT, "evaluator.agent (HarborAgent)")
    _expect_equal(errors, evaluator.get("model"), _CODEX_MODEL, "evaluator.model")
    if "candidate_runtime" in evaluator:
        errors.append("evaluator.candidate_runtime must be absent for the Codex target")
    _expect_equal(errors, evaluator.get("agent_env"), {}, "evaluator.agent_env")
    _expect_equal(errors, evaluator.get("evaluation_split"), "train", "evaluator.evaluation_split")
    _expect_equal(errors, evaluator.get("sampling"), "static", "evaluator.sampling")
    _expect_equal(errors, meta_agent.get("agent"), "codex", "operators.meta_agent.agent")
    _expect_equal(errors, meta_agent.get("model"), _CODEX_MODEL, "operators.meta_agent.model")
    _expect_equal(
        errors,
        meta_agent.get("prompt_path"),
        "target/prompt.md",
        "operators.meta_agent.prompt_path",
    )
    _expect_equal(
        errors,
        meta_agent.get("skills_dir"),
        "target/skills",
        "operators.meta_agent.skills_dir",
    )
    for obsolete_path in ("memory_dir", "tools_dir"):
        if obsolete_path in meta_agent:
            errors.append(f"operators.meta_agent.{obsolete_path} must be absent for the Codex target")

    includes = surface.get("include")
    excludes = surface.get("exclude")
    if not isinstance(includes, list) or not includes or any(not isinstance(item, str) for item in includes):
        errors.append("surface.include must be a non-empty list of path patterns")
    if not isinstance(excludes, list) or any(not isinstance(item, str) for item in excludes):
        errors.append("surface.exclude must be a list of path patterns")
    expected_editable_roots = (
        [
            item[:-3].rstrip("/")
            for item in includes
            if isinstance(item, str) and item.endswith("/**") and "/" not in item[:-3].rstrip("/")
        ]
        if isinstance(includes, list)
        else []
    )
    if meta_agent.get("editable_roots") != expected_editable_roots:
        errors.append("operators.meta_agent.editable_roots must exactly match surface.include roots")

    manifest = _load_json_mapping(
        workspace / "evaluator" / "splits.json",
        errors,
        "evaluator/splits.json",
    )
    if manifest.get("version") != 1 or isinstance(manifest.get("version"), bool):
        errors.append("evaluator/splits.json version must be 1")
    if manifest.get("resolved") is not True:
        errors.append("evaluator/splits.json must be resolved")
    task_mapping = _mapping(manifest.get("tasks"))
    train = _string_tasks(task_mapping, "train", errors)
    gate = _string_tasks(task_mapping, "gate", errors)
    sealed = _string_tasks(task_mapping, "sealed", errors)
    split_lists = {"train": train, "gate": gate, "sealed": sealed}

    for split, names in split_lists.items():
        if len(set(names)) != len(names):
            errors.append(f"evaluator/splits.json tasks.{split} contains duplicate task names")
    all_names = train + gate + sealed
    if len(set(all_names)) != len(all_names):
        errors.append("evaluator/splits.json train/gate/sealed task names must be disjoint")

    counts = _mapping(manifest.get("counts"))
    expected_counts = {name: len(values) for name, values in split_lists.items()}
    for split, count in expected_counts.items():
        if counts.get(split) != count:
            errors.append(f"evaluator/splits.json counts.{split} must equal tasks.{split} length")
    digests = _mapping(manifest.get("digests"))
    for split, names in split_lists.items():
        expected_digest = hashlib.sha256(json.dumps(sorted(names), separators=(",", ":")).encode()).hexdigest()
        if digests.get(split) != expected_digest:
            errors.append(f"evaluator/splits.json digests.{split} must match tasks.{split}")

    train_file = _load_lines(
        workspace / "evaluator" / "tasks" / "train.txt",
        errors,
        "evaluator/tasks/train.txt",
    )
    sealed_file = _load_lines(
        workspace / "evaluator" / "tasks" / "sealed.txt",
        errors,
        "evaluator/tasks/sealed.txt",
    )
    if train_file != train:
        errors.append("evaluator/tasks/train.txt must exactly match splits.json tasks.train")
    if sealed_file != sealed:
        errors.append("evaluator/tasks/sealed.txt must exactly match splits.json tasks.sealed")
    if evaluator.get("tasks_per_round") != len(train):
        errors.append("evaluator.tasks_per_round must equal the frozen train task count")
    if "task_names" in evaluator and evaluator.get("task_names") != train:
        errors.append("evaluator.task_names must exactly match splits.json tasks.train")

    task_report = _mapping(report["tasks"])
    task_report.update(
        train_names=train,
        train_count=len(train),
        gate_count=len(gate),
        sealed_count=len(sealed),
    )

    protected_kwargs = _load_key_values(
        workspace / "evaluator" / "agent.kwargs",
        errors,
        "evaluator/agent.kwargs",
    )
    if protected_kwargs.get("reasoning_effort") != "high":
        errors.append("evaluator/agent.kwargs must protect reasoning_effort=high")
    else:
        _mapping(report["reasoning"])["reasoning_effort"] = "high"

    eval_env = _load_key_values(
        workspace / "evaluator" / "eval.env",
        errors,
        "evaluator/eval.env",
    )
    required_env = {
        "EVOLVE_HARBOR_AGENT": _CODEX_AGENT,
        "EVOLVE_HARBOR_CODEX_SUBSCRIPTION": "1",
        "EVOLVE_HARBOR_EXPECTED_TRIALS": str(len(train)),
        "EVOLVE_HARBOR_MODEL": _CODEX_MODEL,
    }
    for key, expected in required_env.items():
        if eval_env.get(key) != expected:
            errors.append(f"evaluator/eval.env must set {key} to the protected Codex value")

    raw_anchor = evaluator.get("anchor")
    anchor = raw_anchor if isinstance(raw_anchor, dict) else {}
    anchor_report = _mapping(report["anchor"])
    final = anchor.get("final")
    cadence = anchor.get("every_rounds")
    anchor_report["final"] = final if isinstance(final, bool) else None
    anchor_report["every_rounds"] = cadence if isinstance(cadence, int) and not isinstance(cadence, bool) else None
    if expected_anchor == "final":
        if final is not True:
            errors.append("evaluator.anchor.final must be true for a prepared production workspace")
        if cadence != 0 or isinstance(cadence, bool):
            errors.append("evaluator.anchor.every_rounds must be 0 for final-only anchoring")
    elif expected_anchor == "none":
        if len(train) != 3 or len(set(train)) != 3:
            errors.append("a prepared smoke workspace must contain exactly three unique train tasks")
        approved_file = _load_lines(
            workspace / "evaluator" / "smoke-task-names.txt",
            errors,
            "evaluator/smoke-task-names.txt",
        )
        if approved_file != train:
            errors.append("evaluator/smoke-task-names.txt must exactly match the three approved train tasks")
        if final is not False:
            errors.append("evaluator.anchor.final must be false for a prepared smoke workspace")
        if cadence != 0 or isinstance(cadence, bool):
            errors.append("evaluator.anchor.every_rounds must be 0 when smoke anchoring is disabled")
    else:
        errors.append("expected anchor must be final or none")

    report["ok"] = not errors
    return report


def audit_prepared(workspace: Path) -> dict[str, object]:
    """Audit a full prepared Codex workspace with final-only anchoring."""

    return _audit_prepared_for_anchor(workspace, "final")


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(workspace), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _read_archive(workspace: Path, errors: list[str]) -> list[dict[str, Any]]:
    path = workspace / "archive.jsonl"
    if not path.is_file():
        errors.append(f"missing archive.jsonl: {path}")
        return []
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeError):
        errors.append(f"could not read archive.jsonl: {path}")
        return []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"archive.jsonl line {number} is not valid JSON")
            continue
        if not isinstance(event, dict):
            errors.append(f"archive.jsonl line {number} must contain a mapping")
            continue
        events.append(event)
    return events


def _matches(path: str, pattern: str) -> bool:
    if fnmatch(path, pattern):
        return True
    return pattern.endswith("/**") and path == pattern[:-3].rstrip("/")


def _surface_violations(paths: list[str], include: list[str], exclude: list[str]) -> list[str]:
    exclusions = [*exclude, *_IMPLICIT_SURFACE_EXCLUDES]
    return [
        path
        for path in paths
        if any(_matches(path, pattern) for pattern in exclusions)
        or not any(_matches(path, pattern) for pattern in include)
    ]


def _private_evidence_leaks(
    workspace: Path,
    private_tasks: list[str],
    errors: list[str],
) -> list[str]:
    leaks: list[str] = []
    runs = workspace / "runs"
    if not runs.is_dir() or not private_tasks:
        return leaks
    candidates = sorted(
        path
        for path in runs.rglob("*")
        if path.is_file() and _PRIVATE_EVIDENCE_DIRS.intersection(path.relative_to(runs).parts)
    )
    for path in candidates:
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        except OSError:
            errors.append(f"could not read audit evidence path: {path}")
            continue
        if any(task in text for task in private_tasks):
            relative = path.relative_to(workspace).as_posix()
            leaks.append(relative)
            errors.append(f"private task identifier leaked into rollout/trace/feedback text: {relative}")
    return leaks


def _canonical_trial_configs(
    workspace: Path,
    generation: int,
    event: dict[str, Any],
    errors: list[str],
) -> list[tuple[Path, dict[str, Any]]]:
    root = (
        workspace
        / "runs"
        / "evaluations"
        / str(event["purpose"])
        / f"gen-{generation}"
        / f"candidate-{event['candidate_commit']}"
        / f"attempt-{event['attempt']}"
    )
    configs: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(root.glob("jobs/*/*/config.json")):
        configs.append(
            (
                path,
                _load_json_mapping(
                    path,
                    errors,
                    "canonical persisted Harbor trial config",
                ),
            )
        )
    return configs


def _trial_task_identity(config: dict[str, Any]) -> str | None:
    task = _mapping(config.get("task"))
    path = task.get("path")
    if isinstance(path, str) and path:
        return path
    name = task.get("name")
    if isinstance(name, str) and name:
        return name
    return None


def _normalize_task_identity(identity: str, approved: list[str]) -> str | None:
    matches = {
        approved_identity
        for approved_identity in approved
        if identity == approved_identity
        or identity.endswith(f"/{approved_identity}")
        or identity.endswith(f"__{approved_identity}")
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _is_completed_scoreable_trial(trial: dict[str, Any]) -> bool:
    reward = trial.get("reward")
    return (
        trial.get("status") == "benchmark_complete"
        and not trial.get("exception_type")
        and not trial.get("exception_message")
        and not isinstance(reward, bool)
        and isinstance(reward, (int, float))
    )


def _canonical_task_vector_identities(
    event: dict[str, Any],
    generation: int,
    approved: list[str],
    errors: list[str],
) -> list[str]:
    vector = event.get("task_vector")
    if not isinstance(vector, dict):
        errors.append(f"generation {generation} canonical task_vector must be a schema-versioned mapping")
        return []
    if vector.get("schema_version") != 1 or isinstance(vector.get("schema_version"), bool):
        errors.append(f"generation {generation} canonical task_vector schema_version must be 1")
    tasks = vector.get("tasks")
    if not isinstance(tasks, dict):
        errors.append(f"generation {generation} canonical task_vector tasks must be a mapping")
        return []

    raw_identities: list[str] = []
    normalized_identities: list[str] = []
    comparison_identities: list[str] = []
    for task_name, task in tasks.items():
        if not isinstance(task_name, str) or not task_name:
            errors.append(f"generation {generation} canonical task_vector has an invalid task name")
            continue
        if not isinstance(task, dict) or not isinstance(task.get("trials"), list):
            errors.append(f"generation {generation} canonical task_vector has invalid trials for {task_name}")
            continue
        seen_numbers: set[int] = set()
        for trial in task["trials"]:
            raw_identities.append(task_name)
            normalized = _normalize_task_identity(task_name, approved)
            comparison_identities.append(normalized if normalized is not None else task_name)
            if normalized is not None:
                normalized_identities.append(normalized)
            if not isinstance(trial, dict):
                errors.append(f"generation {generation} canonical task_vector has an invalid trial for {task_name}")
                continue
            number = trial.get("trial")
            if isinstance(number, bool) or not isinstance(number, int) or number < 0:
                errors.append(
                    f"generation {generation} canonical task_vector trial number must be a non-negative integer"
                )
            elif number in seen_numbers:
                errors.append(
                    f"generation {generation} canonical task_vector has duplicate trial number {number} "
                    f"for {task_name}"
                )
            else:
                seen_numbers.add(number)
            if not _is_completed_scoreable_trial(trial):
                errors.append(
                    f"generation {generation} canonical task_vector trial for {task_name} "
                    "must be completed and scoreable"
                )

    if len(raw_identities) != 3:
        errors.append(f"generation {generation} canonical task_vector must contain exactly three trial results")
    if (
        len(normalized_identities) != 3
        or len(set(normalized_identities)) != 3
        or set(normalized_identities) != set(approved)
    ):
        errors.append(
            f"generation {generation} canonical task_vector must contain exactly one trial for each approved task"
        )
    return comparison_identities


def audit_smoke(workspace: Path, through_generation: int) -> dict[str, object]:
    """Audit a prepared smoke workspace and canonical evaluations through N."""

    workspace = workspace.expanduser().resolve()
    report = _audit_prepared_for_anchor(workspace, "none")
    _mapping(report["experiment"])["mode"] = "smoke"
    errors = _errors(report)
    lineage = _mapping(report["lineage"])
    lineage["through_generation"] = through_generation

    if isinstance(through_generation, bool) or through_generation < 0:
        errors.append("through_generation must be a non-negative integer")
        report["ok"] = False
        return report

    generations = list(range(through_generation + 1))
    lineage["generations"] = generations
    tag_commits: dict[int, str] = {}
    for generation in generations:
        tag = f"gen/{generation}"
        result = _git(workspace, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}")
        if result.returncode != 0:
            errors.append(f"missing required generation tag {tag}")
        else:
            tag_commits[generation] = result.stdout.strip()

    events = _read_archive(workspace, errors)
    if any(event.get("purpose") == "anchor" or event.get("kind") == "anchor" for event in events):
        errors.append("smoke archive must not contain an anchor event")

    train_names = _mapping(report["tasks"]).get("train_names")
    approved = list(train_names) if isinstance(train_names, list) else []
    complete_events: dict[int, dict[str, Any]] = {}
    linked_events: dict[int, dict[str, Any]] = {}
    parent_generations: dict[int, int] = {}
    vector_task_identities: dict[int, list[str]] = {}
    for generation in generations:
        allowed_purposes = {"candidate", "genesis"} if generation == 0 else {"candidate"}
        generation_events = [
            event
            for event in events
            if event.get("_evolve_mechanism_eval") is True
            and event.get("purpose") in allowed_purposes
            and event.get("generation") == str(generation)
        ]
        canonical = [
            event
            for event in generation_events
            if event.get("status") == "complete" and event.get("selection_eligible") is True
        ]
        if len(canonical) != 1:
            errors.append(
                f"generation {generation} must have exactly one complete selection-eligible canonical evaluation"
            )
            continue
        event = canonical[0]
        complete_events[generation] = event
        linked = True
        if event.get("tag") != f"gen/{generation}":
            errors.append(f"generation {generation} canonical event tag must be gen/{generation}")
            linked = False
        if event.get("genid") != str(generation):
            errors.append(f"generation {generation} canonical event genid must be {generation}")
            linked = False
        candidate_commit = event.get("candidate_commit")
        if (
            not isinstance(candidate_commit, str)
            or not candidate_commit
            or candidate_commit != tag_commits.get(generation)
        ):
            errors.append(
                f"generation {generation} canonical candidate_commit must equal the gen/{generation} tag commit"
            )
            linked = False
        attempt = event.get("attempt")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            errors.append(f"generation {generation} canonical attempt must be a positive integer")
            linked = False
        if "parent" not in event:
            errors.append(f"generation {generation} canonical parent field must be present")
            linked = False
        parent = event.get("parent")
        if generation == 0 and "parent" in event:
            if parent is not None:
                errors.append("generation 0 canonical parent must be null")
                linked = False
        elif generation > 0 and (not isinstance(parent, str) or not parent.isdigit()):
            errors.append(f"generation {generation} canonical parent must name an earlier generation")
            linked = False
        elif generation > 0:
            parent_generation = int(parent)
            if parent_generation >= generation:
                errors.append(f"generation {generation} canonical parent must be earlier and cannot reference itself")
                linked = False
            elif parent_generation not in tag_commits:
                errors.append(f"generation {generation} canonical parent tag gen/{parent_generation} is missing")
                linked = False
            else:
                commit_parent = _git(
                    workspace,
                    "rev-parse",
                    "-q",
                    "--verify",
                    f"refs/tags/gen/{generation}^1",
                )
                if commit_parent.returncode != 0 or commit_parent.stdout.strip() != tag_commits[parent_generation]:
                    errors.append(f"generation {generation} canonical parent must equal the candidate commit parent")
                    linked = False
                else:
                    parent_generations[generation] = parent_generation
        if event.get("expected_trials") != 3 or isinstance(event.get("expected_trials"), bool):
            errors.append(f"generation {generation} canonical expected_trials must be 3")
        members = event.get("task_set_members")
        normalized_members = (
            [_normalize_task_identity(member, approved) for member in members]
            if isinstance(members, list)
            and all(isinstance(member, str) and member for member in members)
            else []
        )
        if (
            not isinstance(members, list)
            or len(members) != 3
            or any(not isinstance(member, str) or not member for member in members)
            or any(member is None for member in normalized_members)
            or len(set(normalized_members)) != 3
            or set(normalized_members) != set(approved)
        ):
            errors.append(
                f"generation {generation} canonical task_set_members must be exactly the three approved train tasks"
            )
        vector_task_identities[generation] = _canonical_task_vector_identities(
            event,
            generation,
            approved,
            errors,
        )
        if linked:
            linked_events[generation] = event
    lineage["complete_evaluations"] = len(complete_events)

    config = _load_yaml_mapping(workspace / "evolve.yaml", errors, "evolve.yaml")
    surface = _mapping(config.get("surface"))
    includes = surface.get("include")
    excludes = surface.get("exclude")
    include_patterns = (
        list(includes) if isinstance(includes, list) and all(isinstance(item, str) for item in includes) else []
    )
    exclude_patterns = (
        list(excludes) if isinstance(excludes, list) and all(isinstance(item, str) for item in excludes) else []
    )
    surface_findings: list[str] = []
    for generation in range(1, through_generation + 1):
        if generation not in linked_events or generation not in parent_generations:
            continue
        parent_generation = parent_generations[generation]
        diff = _git(
            workspace,
            "diff",
            "--name-only",
            f"gen/{parent_generation}",
            f"gen/{generation}",
            "--",
        )
        if diff.returncode != 0:
            errors.append(f"could not compare generation {generation} to parent gen/{parent_generation}")
            continue
        changed = [line for line in diff.stdout.splitlines() if line]
        violations = _surface_violations(changed, include_patterns, exclude_patterns)
        for path in violations:
            finding = f"gen/{generation}:{path}"
            surface_findings.append(finding)
            errors.append(f"generation {generation} changed a path outside the allowed surface: {path}")
    lineage["surface_violations"] = surface_findings

    manifest = _load_json_mapping(
        workspace / "evaluator" / "splits.json",
        errors,
        "evaluator/splits.json",
    )
    task_mapping = _mapping(manifest.get("tasks"))
    private_tasks: list[str] = []
    for split in ("gate", "sealed"):
        members = task_mapping.get(split)
        if isinstance(members, list):
            private_tasks.extend(task for task in members if isinstance(task, str))
    lineage["privacy_leaks"] = _private_evidence_leaks(workspace, private_tasks, errors)

    harbor_config_count = 0
    persisted_reasoning_ok = True
    for generation in generations:
        event = linked_events.get(generation)
        if event is None:
            persisted_reasoning_ok = False
            continue
        configs = _canonical_trial_configs(workspace, generation, event, errors)
        harbor_config_count += len(configs)
        if len(configs) != 3:
            errors.append(f"generation {generation} must have exactly three persisted Harbor trials")
            persisted_reasoning_ok = False
        raw_task_identities: list[str] = []
        normalized_task_identities: list[str] = []
        comparison_task_identities: list[str] = []
        for path, value in configs:
            task_identity = _trial_task_identity(value)
            if task_identity is not None:
                raw_task_identities.append(task_identity)
                normalized = _normalize_task_identity(task_identity, approved)
                comparison_task_identities.append(normalized if normalized is not None else task_identity)
                if normalized is not None:
                    normalized_task_identities.append(normalized)
            kwargs = _mapping(_mapping(value.get("agent")).get("kwargs"))
            if kwargs.get("reasoning_effort") != "high":
                errors.append(f"canonical persisted Harbor trial config must use reasoning_effort=high: {path}")
                persisted_reasoning_ok = False
        if (
            len(raw_task_identities) != 3
            or len(normalized_task_identities) != 3
            or len(set(normalized_task_identities)) != 3
            or set(normalized_task_identities) != set(approved)
        ):
            errors.append(
                f"generation {generation} persisted Harbor trials must have exactly the approved task identities"
            )
            persisted_reasoning_ok = False
        if sorted(comparison_task_identities) != sorted(vector_task_identities.get(generation, [])):
            errors.append(
                f"generation {generation} persisted Harbor task identities must match task_vector task identities"
            )
            persisted_reasoning_ok = False
    lineage["harbor_config_count"] = harbor_config_count
    if not persisted_reasoning_ok:
        _mapping(report["reasoning"])["reasoning_effort"] = None

    report["ok"] = not errors
    return report


def write_report(report: dict[str, object], output: Path | None) -> None:
    """Write a stable JSON report to stdout or an explicit file."""

    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(text)
        return
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a prepared Codex benchmark workspace or completed smoke run.")
    parser.add_argument("workspace", type=Path, metavar="WORKSPACE")
    parser.add_argument("--mode", choices=("prepared", "smoke"), required=True)
    parser.add_argument("--expected-anchor", choices=("final", "none"))
    parser.add_argument("--through-generation", type=int)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.mode == "smoke" and args.through_generation is None:
        parser.error("--through-generation is required with --mode smoke")
    if args.mode == "prepared" and args.through_generation is not None:
        parser.error("--through-generation is only valid with --mode smoke")

    if args.mode == "smoke":
        if args.expected_anchor == "final":
            parser.error("--mode smoke requires --expected-anchor none")
        report = audit_smoke(args.workspace, args.through_generation)
    else:
        expected_anchor = args.expected_anchor or "final"
        report = _audit_prepared_for_anchor(args.workspace, expected_anchor)
    write_report(report, args.output)
    return 0 if report["ok"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
