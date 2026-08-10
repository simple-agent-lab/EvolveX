"""Strict, dependency-free primitives for operator-owned config validation."""

from __future__ import annotations

import math


def config_object(raw: dict[str, object]) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError("config must be a mapping")
    return dict(raw)


def reject_unknown(config: dict[str, object], allowed: set[str]) -> None:
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ValueError("unknown settings: " + ", ".join(unknown))


def positive_int(config: dict[str, object], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{key} must be a positive integer")
    return value


def nonnegative_int(config: dict[str, object], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a nonnegative integer")
    return value


def positive_float(config: dict[str, object], key: str, default: float) -> float:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a positive finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{key} must be a positive finite number")
    return normalized


def boolean(config: dict[str, object], key: str, default: bool) -> bool:
    value = config.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def string(config: dict[str, object], key: str, default: str) -> str:
    value = config.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def string_list(config: dict[str, object], key: str, default: list[str]) -> list[str]:
    value = config.get(key, default)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{key} must be a list of non-empty strings")
    return list(value)


def mapping(config: dict[str, object], key: str, default: dict[str, object]) -> dict[str, object]:
    value = config.get(key, default)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping")
    return dict(value)
