from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")


class EvaluationPaused(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeFingerprint:
    capsule_digest: str
    evaluator_hash: str
    task_set_hash: str

    @property
    def digest(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def mark_preflight(workspace: Path, fingerprint: RuntimeFingerprint, *, epoch: int) -> None:
    if epoch < 0:
        raise ValueError("epoch must be non-negative")
    path = workspace / "runs" / "runtime" / "preflight.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"epoch": epoch, "fingerprint": fingerprint.digest}, sort_keys=True) + "\n")
    temporary.replace(path)


def current_epoch(workspace: Path, fingerprint: RuntimeFingerprint) -> int:
    path = workspace / "runs" / "runtime" / "preflight.json"
    if not path.is_file():
        raise EvaluationPaused("runtime preflight required")
    payload = json.loads(path.read_text())
    if payload.get("fingerprint") != fingerprint.digest:
        raise EvaluationPaused("runtime changed; start a new evaluation epoch")
    epoch = payload.get("epoch")
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
        raise EvaluationPaused("runtime preflight has an invalid epoch")
    return epoch


def attempt_dir(
    workspace: Path,
    *,
    epoch: int,
    purpose: str,
    generation: str,
    candidate_id: str,
    attempt: int,
) -> Path:
    if epoch < 0 or attempt < 1:
        raise ValueError("epoch and attempt must be positive identities")
    for label, value in (("purpose", purpose), ("generation", generation), ("candidate", candidate_id)):
        if not _SAFE_COMPONENT.fullmatch(value) or value in {".", ".."}:
            raise ValueError(f"unsafe {label} identity: {value!r}")
    path = (
        workspace
        / "runs"
        / "evaluations"
        / f"epoch-{epoch}"
        / purpose
        / f"gen-{generation}"
        / f"candidate-{candidate_id}"
        / f"attempt-{attempt}"
    )
    if path.exists():
        raise FileExistsError(f"evaluation attempt already exists: {path}")
    return path
