"""Resolve a secret-free evaluation identity from trusted ``gen/0`` Git inputs."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .. import __version__
from ..evaluator_config import evaluator_repetitions
from ..git import git
from ..runtime_config import (
    ResolvedRuntimeV1,
    RuntimeConfigError,
    load_resolved_runtime,
)
from .datasets import selected_dataset_identity
from .identity import evaluation_split_name

_SENSITIVE_FIELD = re.compile(r"(?i)(?:secret|token|password|passwd|api[_-]?key|credential|authorization|proxy)")


class EvaluationContractResolutionError(RuntimeError):
    def __init__(self, field: str, reason: str):
        self.field = field
        super().__init__(f"cannot resolve evaluation contract field {field}: {reason}")


class ContractMode(StrEnum):
    STRICT = "strict_contract"
    LEGACY_UNVERIFIED = "legacy_unverified"


@dataclass(frozen=True)
class ReceiptVerificationResult:
    certified: bool
    reason: str


@dataclass(frozen=True)
class TrialIdentity:
    task_id: str
    repetition: int
    seed_supported: bool
    seed: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "repetition": self.repetition,
            "seed_supported": self.seed_supported,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class ContractResolutionContext:
    workspace: Path
    candidate_commit: str
    purpose: str
    generation: str
    task_limit: int | None = None


@dataclass(frozen=True)
class EvaluationContractV1:
    schema_version: int
    experiment_id: str
    purpose: str
    generation: str
    candidate_commit: str
    candidate_tree: str
    evaluator_tree: str
    evaluator_config_digest: str
    dataset_content_digest: str
    task_set_digest: str
    task_members: tuple[str, ...]
    split: str
    repetitions: int
    seed_namespace: str
    trial_identities: tuple[TrialIdentity, ...]
    concurrency: int
    runtime_digest: str
    candidate_dependency_digest: str | None
    model_identity: dict[str, str | None]
    retry_policy: dict[str, int]
    framework_version: str

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "purpose": self.purpose,
            "generation": self.generation,
            "candidate_commit": self.candidate_commit,
            "candidate_tree": self.candidate_tree,
            "evaluator_tree": self.evaluator_tree,
            "evaluator_config_digest": self.evaluator_config_digest,
            "dataset_content_digest": self.dataset_content_digest,
            "task_set_digest": self.task_set_digest,
            "task_members": list(self.task_members),
            "split": self.split,
            "repetitions": self.repetitions,
            "seed_namespace": self.seed_namespace,
            "trial_identities": [trial.to_dict() for trial in self.trial_identities],
            "concurrency": self.concurrency,
            "runtime_digest": self.runtime_digest,
            "candidate_dependency_digest": self.candidate_dependency_digest,
            "model_identity": dict(self.model_identity),
            "retry_policy": dict(self.retry_policy),
            "framework_version": self.framework_version,
        }

    @property
    def contract_id(self) -> str:
        return _canonical_digest(self.payload())

    def to_dict(self) -> dict[str, object]:
        return {**self.payload(), "contract_id": self.contract_id}


def resolve_evaluation_contract(context: ContractResolutionContext) -> EvaluationContractV1:
    from ..splits import selected_task_names

    workspace = context.workspace.resolve()
    candidate_commit = _resolve_git_object(workspace, f"{context.candidate_commit}^{{commit}}", "candidate_commit")
    candidate_tree = _resolve_git_object(workspace, f"{candidate_commit}^{{tree}}", "candidate_tree")
    evaluator_tree = _resolve_git_object(workspace, "gen/0:evaluator", "evaluator_tree")
    config = _trusted_config(workspace)
    experiment = config["experiment"]
    evaluator = config["evaluator"]
    experiment_id = str(experiment.get("id") or workspace.name)
    repetitions = _resolve_repetitions(evaluator)
    split = evaluation_split_name(evaluator, context.purpose)
    manifest = _trusted_manifest(workspace)
    if manifest.get("identity_status") != "verified":
        raise EvaluationContractResolutionError(
            "dataset_content_digest", "trusted split manifest has no authoritative content identity"
        )
    _verify_dataset_pin(workspace, manifest)
    task_limit = context.task_limit
    if task_limit is None and evaluator.get("task_scope") == "full":
        task_limit = _integer(
            evaluator.get("tasks_per_round", repetitions),
            "tasks_per_round",
            minimum=1,
        )
    members = tuple(selected_task_names(manifest, split, limit=task_limit))
    if not members:
        raise EvaluationContractResolutionError("task_members", f"split {split!r} contains no selected tasks")
    try:
        dataset_identity = selected_dataset_identity(manifest, members)
    except ValueError as error:
        raise EvaluationContractResolutionError("dataset_content_digest", str(error)) from error
    runtime_pin = _required_git_text(workspace, "gen/0:evaluator/runtime.pin", "runtime_digest").strip()
    if not runtime_pin:
        raise EvaluationContractResolutionError("runtime_digest", "runtime.pin is empty")
    resolved_runtime = _trusted_runtime(workspace)
    if resolved_runtime.digest != runtime_pin:
        raise EvaluationContractResolutionError("runtime_digest", "runtime.pin does not match resolved runtime")
    task_members = dataset_identity.members
    task_set_digest = _canonical_digest(
        {
            "dataset_content_digest": dataset_identity.digest,
            "split": split,
            "task_members": list(task_members),
            "repetitions": repetitions,
        }
    )
    seed_namespace = _canonical_digest(
        {
            "experiment_id": experiment_id,
            "experiment_seed": experiment.get("seed", 0),
            "evaluator_tree": evaluator_tree,
            "dataset_content_digest": dataset_identity.digest,
            "task_set_digest": task_set_digest,
        }
    )
    trials = tuple(
        TrialIdentity(task_id=task, repetition=repetition, seed_supported=False, seed=None)
        for task in task_members
        for repetition in range(repetitions)
    )
    concurrency = _integer(evaluator.get("n_concurrent", repetitions), "concurrency", minimum=1)
    retry_policy = {"max_retries": _integer(evaluator.get("max_retries", 0), "max_retries", minimum=0)}
    semantic_evaluator = _semantic_evaluator_config(evaluator, dataset_identity.resolved_reference)
    return EvaluationContractV1(
        schema_version=1,
        experiment_id=experiment_id,
        purpose=context.purpose,
        generation=str(context.generation),
        candidate_commit=candidate_commit,
        candidate_tree=candidate_tree,
        evaluator_tree=evaluator_tree,
        evaluator_config_digest=_canonical_digest(semantic_evaluator),
        dataset_content_digest=dataset_identity.digest,
        task_set_digest=task_set_digest,
        task_members=task_members,
        split=split,
        repetitions=repetitions,
        seed_namespace=seed_namespace,
        trial_identities=trials,
        concurrency=concurrency,
        runtime_digest=resolved_runtime.digest,
        candidate_dependency_digest=_candidate_dependency_digest(workspace, candidate_commit, resolved_runtime),
        model_identity={
            "agent": _optional_string(evaluator.get("agent")),
            "model": _optional_string(evaluator.get("model")),
            "endpoint_digest": resolved_runtime.endpoint_digest,
        },
        retry_policy=retry_policy,
        framework_version=__version__,
    )


def evaluation_contract_mode(workspace: Path) -> ContractMode:
    resolved_workspace = workspace.resolve()
    manifest = _trusted_manifest(resolved_workspace)
    if manifest.get("identity_status") != "verified":
        return ContractMode.LEGACY_UNVERIFIED
    if _optional_git_text(resolved_workspace, "gen/0:evaluator/runtime.json") is None:
        return ContractMode.LEGACY_UNVERIFIED
    runtime = _trusted_runtime(resolved_workspace)
    runtime_digest = _required_git_text(resolved_workspace, "gen/0:evaluator/runtime.pin", "runtime_digest").strip()
    if runtime.digest != runtime_digest:
        raise EvaluationContractResolutionError("runtime_digest", "runtime.pin does not match resolved runtime")
    return ContractMode.STRICT


def trusted_evaluator_config(workspace: Path) -> dict[str, Any]:
    return dict(_trusted_config(workspace.resolve())["evaluator"])


def verify_candidate_runtime_receipt(
    contract: EvaluationContractV1, receipt: Mapping[str, object] | None
) -> ReceiptVerificationResult:
    if contract.candidate_dependency_digest is None:
        return (
            ReceiptVerificationResult(True, "candidate runtime is not required")
            if receipt is None
            else ReceiptVerificationResult(False, "unexpected candidate runtime receipt")
        )
    if receipt is None:
        return ReceiptVerificationResult(False, "candidate runtime receipt is missing")
    expected: dict[str, object] = {
        "schema_version": 3,
        "variant": "uv",
        "contract_id": contract.contract_id,
        "candidate_commit": contract.candidate_commit,
        "candidate_dependency_digest": contract.candidate_dependency_digest,
        "runtime_digest": contract.runtime_digest,
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            return ReceiptVerificationResult(False, f"candidate runtime receipt {field} mismatch")
    return ReceiptVerificationResult(True, "candidate runtime receipt matches the evaluation contract")


def write_evaluation_contract(path: Path, contract: EvaluationContractV1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(contract.to_dict(), indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _trusted_config(workspace: Path) -> dict[str, dict[str, Any]]:
    text = _required_git_text(workspace, "gen/0:evolve.yaml", "evaluator_config_digest")
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise EvaluationContractResolutionError("evaluator_config_digest", "gen/0 evolve.yaml is invalid") from error
    if not isinstance(loaded, dict):
        raise EvaluationContractResolutionError("evaluator_config_digest", "gen/0 evolve.yaml is not a mapping")
    experiment = loaded.get("experiment")
    evaluator = loaded.get("evaluator")
    if not isinstance(experiment, dict) or not isinstance(evaluator, dict):
        raise EvaluationContractResolutionError(
            "evaluator_config_digest", "gen/0 experiment and evaluator sections must be mappings"
        )
    return {"experiment": experiment, "evaluator": evaluator}


def _trusted_manifest(workspace: Path) -> dict[str, Any]:
    from ..splits import parse_manifest

    text = _required_git_text(workspace, "gen/0:evaluator/splits.json", "dataset_content_digest")
    try:
        return parse_manifest(text, source="gen/0:evaluator/splits.json")
    except (json.JSONDecodeError, RuntimeError) as error:
        raise EvaluationContractResolutionError("dataset_content_digest", str(error)) from error


def _verify_dataset_pin(workspace: Path, manifest: dict[str, Any]) -> None:
    text = _required_git_text(workspace, "gen/0:evaluator/dataset.pin", "dataset_content_digest")
    try:
        pin = json.loads(text)
    except json.JSONDecodeError as error:
        raise EvaluationContractResolutionError(
            "dataset_content_digest", "dataset.pin is legacy or malformed"
        ) from error
    identity = manifest.get("dataset_identity")
    expected_members = sorted(str(name) for split in manifest["tasks"].values() for name in split)
    if (
        not isinstance(pin, dict)
        or pin.get("schema_version") != 1
        or not isinstance(identity, dict)
        or pin.get("source") != identity.get("source")
        or pin.get("digest") != identity.get("digest")
        or pin.get("resolved_reference") != identity.get("resolved_reference")
        or pin.get("members") != expected_members
    ):
        raise EvaluationContractResolutionError(
            "dataset_content_digest", "dataset.pin does not match the trusted split manifest"
        )


def _semantic_evaluator_config(evaluator: dict[str, Any], dataset_reference: str) -> dict[str, Any]:
    redacted = _redact_sensitive(evaluator)
    assert isinstance(redacted, dict)
    normalized: dict[str, Any] = {str(key): value for key, value in redacted.items()}
    normalized["dataset"] = dataset_reference
    normalized.pop("k", None)
    normalized["repetitions"] = evaluator_repetitions(evaluator)
    return normalized


def _redact_sensitive(value: object, *, field: str = "") -> object:
    if field and _SENSITIVE_FIELD.search(field):
        return "<configured>" if value is not None else None
    if isinstance(value, dict):
        return {str(key): _redact_sensitive(item, field=str(key)) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def _candidate_dependency_digest(
    workspace: Path,
    commit: str,
    runtime: ResolvedRuntimeV1,
) -> str | None:
    candidate = runtime.config.candidate
    if candidate is None:
        return None
    if candidate.variant != "uv":
        raise EvaluationContractResolutionError("candidate_dependency_digest", "unsupported candidate runtime")
    relative = PurePosixPath(candidate.project)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise EvaluationContractResolutionError("candidate_dependency_digest", "uv project escapes candidate tree")
    digest = hashlib.sha256()
    for name in ("pyproject.toml", "uv.lock", ".python-version"):
        result = git(workspace, "show", f"{commit}:{relative.as_posix()}/{name}", check=False)
        if result.returncode == 0:
            digest.update(name.encode())
            digest.update(b"\0")
            digest.update(result.stdout.encode())
            digest.update(b"\0")
    return digest.hexdigest()


def _trusted_runtime(workspace: Path) -> ResolvedRuntimeV1:
    text = _required_git_text(workspace, "gen/0:evaluator/runtime.json", "runtime_digest")
    try:
        payload = json.loads(text)
        return load_resolved_runtime(payload)
    except (json.JSONDecodeError, RuntimeConfigError) as error:
        raise EvaluationContractResolutionError("runtime_digest", str(error)) from error


def _resolve_repetitions(evaluator: dict[str, Any]) -> int:
    try:
        return evaluator_repetitions(evaluator)
    except ValueError as error:
        raise EvaluationContractResolutionError("repetitions", str(error)) from error


def _integer(value: object, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvaluationContractResolutionError(field, f"must be an integer of at least {minimum}")
    return value


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _resolve_git_object(workspace: Path, revision: str, field: str) -> str:
    result = git(workspace, "rev-parse", "--verify", revision, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        raise EvaluationContractResolutionError(
            field, result.stderr.strip() or f"Git object {revision!r} is unavailable"
        )
    return result.stdout.strip()


def _required_git_text(workspace: Path, revision: str, field: str) -> str:
    result = git(workspace, "show", revision, check=False)
    if result.returncode != 0:
        raise EvaluationContractResolutionError(
            field, result.stderr.strip() or f"Git object {revision!r} is unavailable"
        )
    return result.stdout


def _optional_git_text(workspace: Path, revision: str) -> str | None:
    result = git(workspace, "show", revision, check=False)
    return result.stdout if result.returncode == 0 else None


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()
