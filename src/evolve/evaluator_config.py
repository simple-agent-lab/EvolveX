from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .runtime_profiles import runtime_profile


def evaluator_repetitions(evaluator: Mapping[str, Any]) -> int:
    has_repetitions = "repetitions" in evaluator
    has_legacy_k = "k" in evaluator
    repetitions = _integer(evaluator.get("repetitions", 1), "repetitions")
    legacy_k = _integer(evaluator["k"], "k") if has_legacy_k else repetitions
    if has_repetitions and has_legacy_k and repetitions != legacy_k:
        raise ValueError("evaluator.repetitions and evaluator.k must be equal")
    return repetitions if has_repetitions else legacy_k


def normalize_evaluator_config(evaluator: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(evaluator)
    normalized["repetitions"] = evaluator_repetitions(evaluator)
    normalized.pop("k", None)
    if "runtime" in evaluator:
        runtime = evaluator["runtime"]
        if not isinstance(runtime, Mapping):
            raise ValueError("evaluator.runtime must be a mapping")
        unknown = sorted(str(key) for key in runtime if key != "profile")
        if unknown:
            raise ValueError("unknown evaluator.runtime fields: " + ", ".join(unknown))
        profile_name = runtime.get("profile")
        if not isinstance(profile_name, str) or not profile_name.strip():
            raise ValueError("evaluator.runtime.profile must be a non-empty string")
        profile = runtime_profile(profile_name.strip())
        if "candidate_runtime" in evaluator:
            raise ValueError(
                "cannot combine evaluator.runtime.profile with evaluator.candidate_runtime"
            )
        engine = evaluator.get("engine")
        if engine is not None and engine != profile.engine:
            raise ValueError(
                f"runtime profile {profile.name} requires evaluator.engine {profile.engine}"
            )
        normalized["runtime"] = {"profile": profile.name}
    return normalized


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"evaluator.{field} must be an integer")
    if not 1 <= value <= 100:
        raise ValueError(f"evaluator.{field} must be between 1 and 100")
    return value
