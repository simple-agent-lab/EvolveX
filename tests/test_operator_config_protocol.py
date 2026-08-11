from __future__ import annotations

import json
import sys

import pytest

from evolve.frozen import sdk
from evolve.frozen.config import Config, integer
from evolve.frozen.interfaces import MutateOperator


class TinyMutate(MutateOperator):
    """Concise operator description."""

    def mutate(self, checkout, observation, ctx):
        raise AssertionError("runtime must not execute")


SCHEMA = Config(
    {
        "attempts": integer(
            default=3,
            minimum=1,
            description="Attempt count.",
        )
    }
)


def test_validate_config_mode_returns_normalized_json(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["operator.py", "--validate-config", "--config", '{"attempts": 4}'],
    )

    sdk.main(TinyMutate, config_schema=SCHEMA)

    assert json.loads(capsys.readouterr().out) == {"attempts": 4}


def test_validate_config_mode_reports_schema_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["operator.py", "--validate-config", "--config", '{"attempts": 0}'],
    )

    with pytest.raises(SystemExit) as exit_info:
        sdk.main(TinyMutate, config_schema=SCHEMA)

    assert exit_info.value.code == 2
    assert "attempts: must be at least 1" in capsys.readouterr().err


def test_validate_config_mode_rejects_non_object_input(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["operator.py", "--validate-config", "--config", "[]"])

    with pytest.raises(SystemExit) as exit_info:
        sdk.main(TinyMutate, config_schema=SCHEMA)

    assert exit_info.value.code == 2
    assert "config must be a JSON object" in capsys.readouterr().err


def test_validate_config_mode_rejects_nonfinite_input(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["operator.py", "--validate-config", "--config", '{"value": NaN}'],
    )

    with pytest.raises(SystemExit) as exit_info:
        sdk.main(TinyMutate, config_schema=SCHEMA)

    assert exit_info.value.code == 2
    assert "config must be valid JSON" in capsys.readouterr().err


def test_describe_mode_reports_stage_description_and_schema(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["operator.py", "--describe"])

    sdk.main(TinyMutate, config_schema=SCHEMA)

    assert json.loads(capsys.readouterr().out) == {
        "config": SCHEMA.describe(),
        "description": "Concise operator description.",
        "stage": "mutate",
    }


def test_description_falls_back_to_module_docstring(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class UndocumentedMutate(MutateOperator):
        def mutate(self, checkout, observation, ctx):
            raise AssertionError("runtime must not execute")

    monkeypatch.setattr(sys, "argv", ["operator.py", "--describe"])
    monkeypatch.setattr(sys.modules[__name__], "__doc__", "Module summary.")

    sdk.main(UndocumentedMutate, config_schema=Config({}))

    assert json.loads(capsys.readouterr().out)["description"] == "Module summary."
