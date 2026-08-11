"""Small declarative schemas for operator configuration."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PathPart = str | int
Normalizer = Callable[[Any], Any]
Refinement = Callable[[dict[str, Any]], None]

_MISSING = object()


@dataclass(frozen=True)
class Violation:
    path: tuple[PathPart, ...]
    message: str


class ConfigError(ValueError):
    def __init__(self, violations: Sequence[Violation]) -> None:
        ordered = tuple(sorted(violations, key=lambda item: _format_path(item.path)))
        self.violations = ordered
        lines = ["configuration is invalid:"]
        lines.extend(
            f"- {_format_path(violation.path)}: {violation.message}" if violation.path else f"- {violation.message}"
            for violation in ordered
        )
        super().__init__("\n".join(lines))


@dataclass(frozen=True)
class _Field:
    kind: str
    required: bool = False
    default: Any = _MISSING
    description: str | None = None
    choices: tuple[Any, ...] | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    items: _Field | None = None
    fields: tuple[tuple[str, _Field], ...] = ()
    additional_properties: bool = False
    normalize_value: Normalizer | None = None
    exported_type: str | None = None


class Config:
    """An immutable top-level operator configuration declaration."""

    def __init__(
        self,
        fields: Mapping[str, _Field],
        *,
        refine: Refinement | None = None,
        _refinements: tuple[Refinement, ...] = (),
    ) -> None:
        checked: list[tuple[str, _Field]] = []
        for name, field in fields.items():
            if not isinstance(name, str) or not name:
                raise ValueError("config field names must be non-empty strings")
            if not isinstance(field, _Field):
                raise TypeError(f"config field {name!r} is not a field declaration")
            checked.append((name, field))
        self._fields = tuple(checked)
        self._refinements = _refinements + ((refine,) if refine is not None else ())

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Validate and return a detached, JSON-compatible config dictionary."""

        if not isinstance(raw, dict):
            raise ConfigError((Violation((), "expected object"),))
        declarations = dict(self._fields)
        violations = [Violation((name,), "unknown field") for name in raw if name not in declarations]
        normalized: dict[str, Any] = {}
        for name, field in self._fields:
            if name in raw:
                value, field_violations = _normalize_field(field, raw[name], (name,))
                violations.extend(field_violations)
                if not field_violations:
                    normalized[name] = value
            elif field.default is not _MISSING:
                normalized[name] = _copy_json(field.default)
            elif field.required:
                violations.append(Violation((name,), "required field is missing"))
        if violations:
            raise ConfigError(violations)
        for refinement in self._refinements:
            try:
                refinement(_copy_json(normalized))
            except ValueError as error:
                raise ConfigError((Violation((), str(error) or "invalid configuration"),)) from error
        return normalized

    def describe(self) -> dict[str, Any]:
        """Export the supported, JSON-compatible inspection schema."""

        description: dict[str, Any] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {name: _describe_field(field) for name, field in self._fields},
        }
        required = [name for name, field in self._fields if field.required]
        if required:
            description["required"] = required
        return description

    def extend(
        self,
        fields: Mapping[str, _Field],
        *,
        refine: Refinement | None = None,
    ) -> Config:
        """Return a schema composed from this schema and new unique fields."""

        existing = dict(self._fields)
        for name in fields:
            if name in existing:
                raise ValueError(f"duplicate config field: {name}")
        return Config(
            {**existing, **fields},
            refine=refine,
            _refinements=self._refinements,
        )


def string(
    *,
    required: bool = False,
    default: Any = _MISSING,
    choices: Sequence[str] | None = None,
    description: str | None = None,
) -> _Field:
    return _make_field(
        "string",
        required=required,
        default=default,
        choices=tuple(choices) if choices is not None else None,
        description=description,
    )


def integer(
    *,
    required: bool = False,
    default: Any = _MISSING,
    minimum: int | None = None,
    maximum: int | None = None,
    choices: Sequence[int] | None = None,
    description: str | None = None,
) -> _Field:
    return _make_field(
        "integer",
        required=required,
        default=default,
        minimum=minimum,
        maximum=maximum,
        choices=tuple(choices) if choices is not None else None,
        description=description,
    )


def number(
    *,
    required: bool = False,
    default: Any = _MISSING,
    minimum: int | float | None = None,
    maximum: int | float | None = None,
    choices: Sequence[int | float] | None = None,
    description: str | None = None,
) -> _Field:
    return _make_field(
        "number",
        required=required,
        default=default,
        minimum=minimum,
        maximum=maximum,
        choices=tuple(choices) if choices is not None else None,
        description=description,
    )


def boolean(
    *,
    required: bool = False,
    default: Any = _MISSING,
    description: str | None = None,
) -> _Field:
    return _make_field("boolean", required=required, default=default, description=description)


def array(
    items: _Field,
    *,
    required: bool = False,
    default: Any = _MISSING,
    description: str | None = None,
) -> _Field:
    if not isinstance(items, _Field):
        raise TypeError("array items must be a field declaration")
    return _make_field(
        "array",
        required=required,
        default=default,
        description=description,
        items=items,
    )


def object(
    fields: Mapping[str, _Field] | None = None,
    *,
    additional_properties: bool = False,
    required: bool = False,
    default: Any = _MISSING,
    description: str | None = None,
) -> _Field:
    return _make_field(
        "object",
        required=required,
        default=default,
        description=description,
        fields=tuple((fields or {}).items()),
        additional_properties=additional_properties,
    )


def json_value(
    *,
    required: bool = False,
    default: Any = _MISSING,
    description: str | None = None,
) -> _Field:
    return _make_field("json", required=required, default=default, description=description)


def custom(
    normalize: Normalizer,
    *,
    exported_type: str,
    required: bool = False,
    default: Any = _MISSING,
    description: str,
) -> _Field:
    if exported_type not in {"string", "integer", "number", "boolean", "array", "object"}:
        raise ValueError("unsupported custom exported_type")
    return _make_field(
        "custom",
        required=required,
        default=default,
        description=description,
        normalize_value=normalize,
        exported_type=exported_type,
    )


def _make_field(kind: str, **values: Any) -> _Field:
    field = _Field(kind=kind, **values)
    if field.required and field.default is not _MISSING:
        raise ValueError("required field cannot have a default")
    if field.minimum is not None and field.maximum is not None and field.minimum > field.maximum:
        raise ValueError("minimum cannot exceed maximum")
    if field.default is not _MISSING:
        _copy_json(field.default)
        _, violations = _normalize_field(field, field.default, ())
        if violations:
            raise ValueError(f"default is invalid: {violations[0].message}")
    return field


def _normalize_field(field: _Field, value: Any, path: tuple[PathPart, ...]) -> tuple[Any, list[Violation]]:
    if field.kind == "custom":
        try:
            assert field.normalize_value is not None
            value = field.normalize_value(value)
        except (TypeError, ValueError) as error:
            return None, [Violation(path, str(error) or "invalid value")]
        if not _is_json(value):
            return None, [Violation(path, "normalized value must be JSON-compatible")]
        return _copy_json(value), []
    if field.kind == "string":
        if not isinstance(value, str) or not value.strip():
            return None, [Violation(path, "expected non-empty string")]
    elif field.kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return None, [Violation(path, "expected integer")]
    elif field.kind == "number":
        if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
            return None, [Violation(path, "expected finite number")]
        value = float(value)
    elif field.kind == "boolean":
        if not isinstance(value, bool):
            return None, [Violation(path, "expected boolean")]
    elif field.kind == "array":
        if not isinstance(value, list):
            return None, [Violation(path, "expected array")]
        output: list[Any] = []
        violations: list[Violation] = []
        assert field.items is not None
        for index, item in enumerate(value):
            normalized, item_violations = _normalize_field(field.items, item, (*path, index))
            violations.extend(item_violations)
            if not item_violations:
                output.append(normalized)
        return output, violations
    elif field.kind == "object":
        if not isinstance(value, dict):
            return None, [Violation(path, "expected object")]
        declarations = dict(field.fields)
        output = {}
        violations = []
        for name in value:
            if not isinstance(name, str):
                violations.append(Violation(path, "object keys must be strings"))
            elif name not in declarations:
                if field.additional_properties:
                    if _is_json(value[name]):
                        output[name] = _copy_json(value[name])
                    else:
                        violations.append(Violation((*path, name), "expected JSON value"))
                else:
                    violations.append(Violation((*path, name), "unknown field"))
        for name, declaration in field.fields:
            if name in value:
                normalized, item_violations = _normalize_field(declaration, value[name], (*path, name))
                violations.extend(item_violations)
                if not item_violations:
                    output[name] = normalized
            elif declaration.default is not _MISSING:
                output[name] = _copy_json(declaration.default)
            elif declaration.required:
                violations.append(Violation((*path, name), "required field is missing"))
        return output, violations
    elif field.kind == "json":
        if not _is_json(value):
            return None, [Violation(path, "expected JSON value")]
        return _copy_json(value), []
    if field.choices is not None and value not in field.choices:
        expected = ", ".join(json.dumps(choice) for choice in field.choices)
        return None, [Violation(path, f"expected one of {expected}")]
    if field.minimum is not None and value < field.minimum:  # type: ignore[operator]
        return None, [Violation(path, f"must be at least {field.minimum}")]
    if field.maximum is not None and value > field.maximum:  # type: ignore[operator]
        return None, [Violation(path, f"must be at most {field.maximum}")]
    return value, []


def _describe_field(field: _Field) -> dict[str, Any]:
    result: dict[str, Any] = {"type": field.exported_type if field.kind == "custom" else field.kind}
    if field.description is not None:
        result["description"] = field.description
    if field.default is not _MISSING:
        result["default"] = _copy_json(field.default)
    if field.choices is not None:
        result["enum"] = list(field.choices)
    if field.minimum is not None:
        result["minimum"] = field.minimum
    if field.maximum is not None:
        result["maximum"] = field.maximum
    if field.kind == "array":
        assert field.items is not None
        result["items"] = _describe_field(field.items)
    if field.kind == "object":
        result["additionalProperties"] = field.additional_properties
        if field.fields:
            result["properties"] = {name: _describe_field(declaration) for name, declaration in field.fields}
            required = [name for name, declaration in field.fields if declaration.required]
            if required:
                result["required"] = required
    return result


def _is_json(value: Any) -> bool:
    if value is None or isinstance(value, bool | str | int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json(item) for key, item in value.items())
    return False


def _copy_json(value: Any) -> Any:
    if not _is_json(value):
        raise ValueError("value must be JSON-compatible")
    return json.loads(json.dumps(value, allow_nan=False))


def _format_path(path: tuple[PathPart, ...]) -> str:
    rendered = ""
    for part in path:
        rendered += f"[{part}]" if isinstance(part, int) else (f".{part}" if rendered else part)
    return rendered
