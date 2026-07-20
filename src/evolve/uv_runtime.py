from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evaluation import Outcome


@dataclass(frozen=True)
class UvRuntimeConfig:
    variant: str
    project: Path
    project_relative: str


@dataclass(frozen=True)
class RuntimeMount:
    source: Path
    target: str
    read_only: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "bind",
            "source": str(self.source),
            "target": self.target,
            "read_only": self.read_only,
        }


@dataclass(frozen=True)
class CandidateRuntimeResult:
    variant: str | None
    project: str | None
    environment: tuple[tuple[str, str], ...] = ()
    mounts: tuple[RuntimeMount, ...] = ()
    outcome: Outcome | None = None
    reason: str | None = None
    receipt_path: Path | None = None

    @property
    def ready(self) -> bool:
        return self.outcome is None

    def environment_json(self) -> str:
        return json.dumps(dict(self.environment), sort_keys=True, separators=(",", ":"))

    def mounts_json(self) -> str:
        return json.dumps(
            [mount.to_dict() for mount in self.mounts],
            sort_keys=True,
            separators=(",", ":"),
        )


def candidate_runtime_config(
    checkout: Path, evaluator: dict[str, Any]
) -> UvRuntimeConfig | None:
    value = evaluator.get("candidate_runtime")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("evaluator.candidate_runtime must be a mapping")
    if value.get("variant") != "uv":
        raise ValueError(
            f"unsupported candidate runtime variant: {value.get('variant')!r}"
        )
    raw_project = value.get("project")
    if not isinstance(raw_project, str) or not raw_project.strip():
        raise ValueError("evaluator.candidate_runtime.project must be a relative path")
    relative = Path(raw_project)
    if relative.is_absolute():
        raise ValueError("candidate runtime project must be relative")
    root = checkout.resolve()
    project = (root / relative).resolve()
    try:
        project.relative_to(root)
    except ValueError:
        raise ValueError("candidate runtime project escapes checkout") from None
    return UvRuntimeConfig("uv", project, project.relative_to(root).as_posix())
