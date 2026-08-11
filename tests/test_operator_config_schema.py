from __future__ import annotations

import math
from collections.abc import Callable

import pytest

from evolve.frozen.config import (
    Config,
    ConfigError,
    array,
    boolean,
    custom,
    integer,
    json_value,
    number,
    object,
    string,
)


def test_config_normalizes_defaults_and_omits_absent_optional_fields() -> None:
    schema = Config(
        {
            "name": string(required=True),
            "attempts": integer(default=3, minimum=1),
            "ratio": number(default=1, minimum=0, maximum=1),
            "enabled": boolean(default=False),
            "labels": array(string(), default=[]),
            "note": string(),
        }
    )

    first = schema.normalize({"name": "demo"})
    second = schema.normalize({"name": "demo"})

    assert first == {
        "name": "demo",
        "attempts": 3,
        "ratio": 1.0,
        "enabled": False,
        "labels": [],
    }
    assert "note" not in first
    assert isinstance(first["ratio"], float)
    assert first["labels"] is not second["labels"]


def test_defaults_use_the_same_normalization_as_explicit_values() -> None:
    paths = custom(
        lambda value: [value] if isinstance(value, str) else value,
        exported_type="array",
        default="target/prompt.md",
        description="Paths to edit.",
    )
    schema = Config(
        {
            "paths": paths,
            "nested": object({"ratio": number(default=1)}, default={}),
        }
    )

    expected = {"paths": ["target/prompt.md"], "nested": {"ratio": 1.0}}
    assert schema.normalize({}) == expected
    assert schema.normalize({"paths": "target/prompt.md", "nested": {}}) == expected
    assert schema.describe()["properties"]["paths"]["default"] == ["target/prompt.md"]


@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_integer_rejects_non_integer_types(value: object) -> None:
    with pytest.raises(ConfigError, match="count: expected integer"):
        Config({"count": integer(required=True)}).normalize({"count": value})


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan, True])
def test_number_requires_a_finite_non_boolean_number(value: object) -> None:
    with pytest.raises(ConfigError, match="ratio: expected finite number"):
        Config({"ratio": number(required=True)}).normalize({"ratio": value})


def test_declarations_reject_required_defaults_and_invalid_defaults() -> None:
    with pytest.raises(ValueError, match="required field cannot have a default"):
        string(required=True, default="x")
    with pytest.raises(ValueError, match="default is invalid"):
        integer(default=0, minimum=1)


@pytest.mark.parametrize(
    "declare",
    [
        lambda: number(minimum=math.nan),
        lambda: number(maximum=math.inf),
        lambda: number(choices=(math.nan,)),
        lambda: integer(minimum=True),
        lambda: integer(choices=(1.0,)),
        lambda: string(choices=(1,)),
    ],
)
def test_declarations_reject_invalid_bounds_and_choices(declare: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        declare()


def test_number_choices_are_normalized_in_descriptions() -> None:
    schema = Config({"ratio": number(default=1, choices=(1, 2))})

    description = schema.describe()["properties"]["ratio"]
    assert description == {
        "type": "number",
        "default": 1.0,
        "enum": [1.0, 2.0],
    }
    assert isinstance(description["default"], float)
    assert all(isinstance(choice, float) for choice in description["enum"])


def test_nested_arrays_objects_and_open_json_are_copied() -> None:
    schema = Config(
        {
            "items": array(object({"name": string(required=True)}), required=True),
            "metadata": object(additional_properties=True, required=True),
            "value": json_value(required=True),
        }
    )
    raw = {
        "items": [{"name": "one"}],
        "metadata": {"nested": [1, True, None]},
        "value": {"key": "value"},
    }

    normalized = schema.normalize(raw)

    assert normalized == raw
    assert normalized is not raw
    assert normalized["metadata"] is not raw["metadata"]


def test_extend_composes_fields_and_rejects_duplicates() -> None:
    base = Config({"runner": string(default="local")})
    combined = base.extend({"attempts": integer(default=1)})

    assert combined.normalize({}) == {"runner": "local", "attempts": 1}
    with pytest.raises(ValueError, match="duplicate config field: runner"):
        base.extend({"runner": string(default="harbor")})


def test_errors_are_sorted_path_aware_and_do_not_echo_values() -> None:
    schema = Config(
        {
            "count": integer(required=True),
            "mode": string(choices=("safe",)),
            "items": array(integer(), default=[]),
        }
    )
    with pytest.raises(ConfigError) as caught:
        schema.normalize({"secret": "do-not-print", "mode": "unsafe", "items": [1, "bad"]})

    assert str(caught.value).splitlines() == [
        "configuration is invalid:",
        "- count: required field is missing",
        "- items[1]: expected integer",
        '- mode: expected one of "safe"',
        "- secret: unknown field",
    ]
    assert "do-not-print" not in str(caught.value)


def test_custom_normalizes_one_field_and_requires_json_output() -> None:
    schema = Config(
        {
            "paths": custom(
                lambda value: [value] if isinstance(value, str) else value,
                exported_type="array",
                required=True,
                description="Paths to edit.",
            )
        }
    )
    assert schema.normalize({"paths": "target/prompt.md"}) == {"paths": ["target/prompt.md"]}

    invalid = Config(
        {
            "value": custom(
                lambda _value: object(),
                exported_type="object",
                required=True,
                description="A value.",
            )
        }
    )
    with pytest.raises(ConfigError, match="value: normalized value must be JSON-compatible"):
        invalid.normalize({"value": {}})


def test_refine_validates_a_copy_without_mutating_output() -> None:
    def refine(config: dict[str, object]) -> None:
        config["mutated"] = True
        if config["minimum"] > config["maximum"]:  # type: ignore[operator]
            raise ValueError("minimum must not exceed maximum")

    schema = Config(
        {
            "minimum": integer(required=True),
            "maximum": integer(required=True),
        },
        refine=refine,
    )

    assert schema.normalize({"minimum": 1, "maximum": 2}) == {
        "minimum": 1,
        "maximum": 2,
    }
    with pytest.raises(ConfigError, match="minimum must not exceed maximum"):
        schema.normalize({"minimum": 3, "maximum": 2})


def test_describe_exports_the_small_supported_schema_subset() -> None:
    schema = Config(
        {
            "mode": string(
                default="safe",
                choices=("safe", "fast"),
                description="Execution mode.",
            ),
            "count": integer(required=True, minimum=1, maximum=5),
            "metadata": object(additional_properties=True),
        }
    )

    assert schema.describe() == {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "mode": {
                "type": "string",
                "description": "Execution mode.",
                "default": "safe",
                "enum": ["safe", "fast"],
            },
            "count": {"type": "integer", "minimum": 1, "maximum": 5},
            "metadata": {"type": "object", "additionalProperties": True},
        },
        "required": ["count"],
    }
