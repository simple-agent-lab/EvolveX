from pathlib import Path

import pytest

from evolve.operator_library import (
    OperatorLibraryError,
    describe_operator,
    discover_operators,
    resolve_operator,
    validate_operator_config,
)


def test_discovery_derives_identity_without_importing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "library"
    (root / "mutate").mkdir(parents=True)
    (root / "mutate" / "critic_editor.py").write_text("raise AssertionError('must not import')\n")
    (root / "mutate" / "_shared.py").write_text("raise AssertionError('helper')\n")

    found = discover_operators(root)

    assert set(found) == {("mutate", "critic_editor")}
    assert found[("mutate", "critic_editor")].source.name == "critic_editor.py"


def test_discovery_rejects_invalid_operator_filename(tmp_path: Path) -> None:
    root = tmp_path / "library"
    (root / "mutate").mkdir(parents=True)
    (root / "mutate" / "Bad-Name.py").touch()

    with pytest.raises(OperatorLibraryError, match="Bad-Name.py"):
        discover_operators(root)


def test_discovery_rejects_unknown_stage_directory(tmp_path: Path) -> None:
    root = tmp_path / "library"
    (root / "custom_stage").mkdir(parents=True)

    with pytest.raises(OperatorLibraryError, match="custom_stage"):
        discover_operators(root)


def test_discovery_rejects_non_underscore_root_python_helper(tmp_path: Path) -> None:
    root = tmp_path / "library"
    root.mkdir()
    (root / "gepa_support.py").touch()

    with pytest.raises(OperatorLibraryError, match="gepa_support.py"):
        discover_operators(root)


def test_discovery_ignores_pycache(tmp_path: Path) -> None:
    root = tmp_path / "library"
    (root / "mutate").mkdir(parents=True)
    (root / "mutate" / "critic_editor.py").touch()
    (root / "mutate" / "__pycache__").mkdir()
    (root / "mutate" / "__pycache__" / "Bad-Name.pyc").touch()

    assert set(discover_operators(root)) == {("mutate", "critic_editor")}


def test_discovery_allows_shared_helpers(tmp_path: Path) -> None:
    root = tmp_path / "library"
    (root / "_shared").mkdir(parents=True)
    (root / "_shared" / "gepa.py").touch()
    (root / "README.md").touch()

    assert discover_operators(root) == {}


def test_subprocess_inspection_describes_and_validates_operator_config(tmp_path: Path) -> None:
    root = _library_with_operator(tmp_path, _sdk_operator_script())
    operator = resolve_operator("mutate", "critic_editor", root)

    assert validate_operator_config(operator, {"attempts": 2}) == {"attempts": 2}
    assert describe_operator(operator) == {
        "config_validation": True,
        "description": "Edits a candidate after reviewing evidence.",
        "stage": "mutate",
    }


def test_subprocess_inspection_reports_timeout_with_identity(tmp_path: Path) -> None:
    root = _library_with_operator(tmp_path, "import time\ntime.sleep(1)\n")
    operator = resolve_operator("mutate", "critic_editor", root)

    with pytest.raises(OperatorLibraryError, match=r"mutate/critic_editor.*timed out"):
        describe_operator(operator, timeout_s=0.01)


def test_subprocess_inspection_reports_nonzero_exit_with_stderr_tail(tmp_path: Path) -> None:
    root = _library_with_operator(tmp_path, "import sys\nsys.stderr.write('broken entry')\nraise SystemExit(7)\n")
    operator = resolve_operator("mutate", "critic_editor", root)

    with pytest.raises(OperatorLibraryError, match=r"mutate/critic_editor.*broken entry"):
        describe_operator(operator)


def test_subprocess_inspection_rejects_malformed_stdout(tmp_path: Path) -> None:
    root = _library_with_operator(tmp_path, "print('not json')\n")
    operator = resolve_operator("mutate", "critic_editor", root)

    with pytest.raises(OperatorLibraryError, match=r"mutate/critic_editor.*JSON"):
        describe_operator(operator)


def test_subprocess_validation_reports_missing_validator(tmp_path: Path) -> None:
    root = _library_with_operator(tmp_path, _sdk_operator_script(include_validator=False))
    operator = resolve_operator("mutate", "critic_editor", root)

    with pytest.raises(OperatorLibraryError, match=r"mutate/critic_editor.*does not support config validation"):
        validate_operator_config(operator, {})


def test_discovery_does_not_import_operator_but_inspection_subprocess_does(tmp_path: Path) -> None:
    marker = tmp_path / "operator-imported"
    root = _library_with_operator(
        tmp_path, f"from pathlib import Path\nPath({str(marker)!r}).write_text('yes')\nprint('{{}}')\n"
    )

    operator = resolve_operator("mutate", "critic_editor", root)

    assert not marker.exists()
    assert describe_operator(operator) == {}
    assert marker.read_text() == "yes"


def _library_with_operator(tmp_path: Path, script: str) -> Path:
    root = tmp_path / "library"
    (root / "mutate").mkdir(parents=True)
    (root / "mutate" / "critic_editor.py").write_text(script)
    return root


def _sdk_operator_script(*, include_validator: bool = True) -> str:
    validator = (
        "\n\ndef validate(raw):\n    return {'attempts': int(raw.get('attempts', 3))}\n" if include_validator else ""
    )
    call = "sdk.main(CriticEditor, validate_config=validate)" if include_validator else "sdk.main(CriticEditor)"
    return (
        "from evolve.frozen import sdk\n"
        "from evolve.frozen.interfaces import MutateOperator\n\n"
        "class CriticEditor(MutateOperator):\n"
        '    """Edits a candidate after reviewing evidence."""\n\n'
        "    def mutate(self, checkout, observation, ctx):\n"
        "        raise AssertionError('runtime must not execute')\n"
        f"{validator}\n"
        f"{call}\n"
    )
