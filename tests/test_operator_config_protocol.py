import json
import sys

import pytest

from evolve.frozen import sdk
from evolve.frozen.interfaces import MutateOperator


def test_validate_config_mode_returns_normalized_json(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class TinyMutate(MutateOperator):
        def mutate(self, checkout, observation, ctx):
            raise AssertionError("runtime must not execute")

    def validate(raw: dict[str, object]) -> dict[str, object]:
        return {"attempts": int(raw.get("attempts", 3))}

    monkeypatch.setattr(sys, "argv", ["operator.py", "--validate-config", "--config", '{"attempts": 4}'])
    sdk.main(TinyMutate, validate_config=validate)

    assert json.loads(capsys.readouterr().out) == {"attempts": 4}


def test_validate_config_mode_rejects_missing_validator(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class TinyMutate(MutateOperator):
        def mutate(self, checkout, observation, ctx):
            raise AssertionError("runtime must not execute")

    monkeypatch.setattr(sys, "argv", ["operator.py", "--validate-config"])

    with pytest.raises(SystemExit) as exit_info:
        sdk.main(TinyMutate)

    assert exit_info.value.code == 2
    assert "does not support config validation" in capsys.readouterr().err


def test_validate_config_mode_rejects_non_object_input(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["operator.py", "--validate-config", "--config", "[]"])

    with pytest.raises(SystemExit) as exit_info:
        sdk.main(object, validate_config=lambda raw: raw)

    assert exit_info.value.code == 2
    assert "config must be a JSON object" in capsys.readouterr().err


def test_validate_config_mode_rejects_non_object_normalized_output(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["operator.py", "--validate-config"])

    with pytest.raises(SystemExit) as exit_info:
        sdk.main(object, validate_config=lambda raw: [])

    assert exit_info.value.code == 2
    assert "config validator must return a JSON object" in capsys.readouterr().err


def test_validate_config_mode_reports_validator_exception(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def validate(raw: dict[str, object]) -> dict[str, object]:
        raise ValueError("attempts must be positive")

    monkeypatch.setattr(sys, "argv", ["operator.py", "--validate-config"])

    with pytest.raises(SystemExit) as exit_info:
        sdk.main(object, validate_config=validate)

    assert exit_info.value.code == 2
    assert "attempts must be positive" in capsys.readouterr().err


def test_describe_mode_reports_stage_description_and_validation(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class TinyMutate(MutateOperator):
        """Concise operator description."""

        def mutate(self, checkout, observation, ctx):
            raise AssertionError("runtime must not execute")

    monkeypatch.setattr(sys, "argv", ["operator.py", "--describe"])
    sdk.main(TinyMutate, validate_config=lambda raw: raw)

    assert json.loads(capsys.readouterr().out) == {
        "config_validation": True,
        "description": "Concise operator description.",
        "stage": "mutate",
    }
