from importlib.resources.abc import Traversable
from io import BytesIO, StringIO
from pathlib import Path

import pytest

from evolve.composition.catalog import (
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


def test_discovery_rejects_symlinked_named_operator(tmp_path: Path) -> None:
    root = tmp_path / "library"
    stage = root / "mutate"
    stage.mkdir(parents=True)
    external = tmp_path / "external.py"
    external.write_text("print('{}')\n")
    (stage / "critic_editor.py").symlink_to(external)

    with pytest.raises(OperatorLibraryError, match=r"symlink.*mutate/critic_editor\.py"):
        discover_operators(root)


def test_discovery_rejects_symlinked_stage_directory(tmp_path: Path) -> None:
    root = tmp_path / "library"
    external = tmp_path / "external"
    external.mkdir(parents=True)
    (external / "critic_editor.py").write_text("print('{}')\n")
    root.mkdir()
    (root / "mutate").symlink_to(external, target_is_directory=True)

    with pytest.raises(OperatorLibraryError, match=r"symlink.*mutate"):
        discover_operators(root)


def test_discovery_rejects_symlinked_library_root(tmp_path: Path) -> None:
    external = tmp_path / "external"
    (external / "mutate").mkdir(parents=True)
    (external / "mutate" / "critic_editor.py").write_text("print('{}')\n")
    root = tmp_path / "library"
    root.symlink_to(external, target_is_directory=True)

    with pytest.raises(OperatorLibraryError, match=r"symlink.*library"):
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


def test_contract_only_traversable_discovers_and_inspects_with_shared_helper() -> None:
    root = _resource_tree(
        {
            "mutate": {
                "critic_editor.py": (
                    "from library._shared.helper import answer\nimport json\nprint(json.dumps({'answer': answer}))\n"
                ),
            },
            "_shared": {"helper.py": "answer = 42\n"},
        }
    )

    operator = resolve_operator("mutate", "critic_editor", root)

    assert describe_operator(operator) == {"answer": 42}


def test_source_library_wins_over_later_regular_library_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hostile = tmp_path / "hostile"
    (hostile / "library").mkdir(parents=True)
    (hostile / "library/__init__.py").write_text("")
    monkeypatch.setenv("PYTHONPATH", str(hostile))

    description = describe_operator(resolve_operator("mutate", "hyperagents"))

    assert description["stage"] == "mutate"


def test_subprocess_inspection_describes_and_validates_operator_config(tmp_path: Path) -> None:
    root = _library_with_operator(tmp_path, _sdk_operator_script())
    operator = resolve_operator("mutate", "critic_editor", root)

    assert validate_operator_config(operator, {"attempts": 2}) == {"attempts": 2}
    assert describe_operator(operator) == {
        "config": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"attempts": {"type": "integer", "default": 3}},
        },
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


def test_subprocess_validation_wraps_non_json_config(tmp_path: Path) -> None:
    root = _library_with_operator(tmp_path, _sdk_operator_script())
    operator = resolve_operator("mutate", "critic_editor", root)

    with pytest.raises(OperatorLibraryError, match=r"mutate/critic_editor.*not JSON-serializable"):
        validate_operator_config(operator, {"attempts": {1}})


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_subprocess_validation_rejects_nested_nonfinite_config(tmp_path: Path, nonfinite: float) -> None:
    root = _library_with_operator(tmp_path, _sdk_operator_script())
    operator = resolve_operator("mutate", "critic_editor", root)

    with pytest.raises(OperatorLibraryError, match=r"mutate/critic_editor.*not JSON-serializable"):
        validate_operator_config(operator, {"opaque": {"temperature": nonfinite}})


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_subprocess_inspection_rejects_nonfinite_json_constant(tmp_path: Path, constant: str) -> None:
    root = _library_with_operator(tmp_path, f"print('{{\"value\": {constant}}}')\n")
    operator = resolve_operator("mutate", "critic_editor", root)

    with pytest.raises(OperatorLibraryError, match=r"mutate/critic_editor.*malformed JSON"):
        describe_operator(operator)


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


def _sdk_operator_script() -> str:
    return (
        "from evolve.frozen import sdk\n"
        "from evolve.frozen.config import Config, integer\n"
        "from evolve.frozen.interfaces import MutateOperator\n\n"
        "class CriticEditor(MutateOperator):\n"
        '    """Edits a candidate after reviewing evidence."""\n\n'
        "    def mutate(self, checkout, observation, ctx):\n"
        "        raise AssertionError('runtime must not execute')\n"
        "\nSCHEMA = Config({'attempts': integer(default=3)})\n\n"
        "sdk.main(CriticEditor, config_schema=SCHEMA)\n"
    )


class _MemoryTraversable(Traversable):
    def __init__(self, name: str, children: dict[str, "_MemoryTraversable"] | None = None, data: bytes | None = None):
        self._name = name
        self._children = children
        self._data = data

    @property
    def name(self) -> str:
        return self._name

    def iterdir(self):
        return iter((self._children or {}).values())

    def is_dir(self) -> bool:
        return self._children is not None

    def is_file(self) -> bool:
        return self._data is not None

    def joinpath(self, *descendants: str):
        entry: Traversable = self
        for descendant in descendants:
            if not isinstance(entry, _MemoryTraversable) or entry._children is None:
                return _MemoryTraversable(descendant)
            entry = entry._children.get(descendant, _MemoryTraversable(descendant))
        return entry

    def open(self, mode: str = "r", *args, **kwargs):
        if self._data is None:
            raise FileNotFoundError(self.name)
        if "b" in mode:
            return BytesIO(self._data)
        return StringIO(self._data.decode())


def _resource_tree(data: dict[str, object], name: str = "library") -> _MemoryTraversable:
    children: dict[str, _MemoryTraversable] = {}
    for child_name, value in data.items():
        if isinstance(value, dict):
            children[child_name] = _resource_tree(value, child_name)
        else:
            children[child_name] = _MemoryTraversable(child_name, data=str(value).encode())
    return _MemoryTraversable(name, children=children)
