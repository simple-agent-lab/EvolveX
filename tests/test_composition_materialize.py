import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from evolve.composition import ResolvedOperator, resolve_builtin_recipe, resolve_recipe
from evolve.composition.materialize import materialize_operators
from evolve.config import load_config, render_yaml

ROOT = Path(__file__).resolve().parents[1]


def test_materialization_contains_selected_operators_and_runtime_helpers_only() -> None:
    resolved = resolve_builtin_recipe("hill_climb")

    materialized = materialize_operators(resolved.operators)

    assert "operators/select.py" in materialized.files
    assert "operators/analyze.py" in materialized.files
    assert "operators/mutate.py" in materialized.files
    assert "library/__init__.py" in materialized.files
    assert "library/select/_config.py" in materialized.files
    assert "library/analyze/_config.py" in materialized.files
    assert "library/mutate/_config.py" in materialized.files
    assert "library/_shared/runners/local.py" in materialized.files
    assert not any(path.startswith("library/_methods_shared/") for path in materialized.files)
    assert "library/mutate/_support/workspace.py" in materialized.files
    assert "library/mutate/_skeleton.py" not in materialized.files
    assert all(
        path.removeprefix("library/mutate/").split("/", 1)[0].startswith("_")
        for path in materialized.files
        if path.startswith("library/mutate/")
    )
    assert not any(path == "library/analyze/ahe.py" for path in materialized.files)
    assert "library/README.md" not in materialized.files
    assert "library/PROTOCOL.md" not in materialized.files
    assert "alternatives" not in str(materialized.files["operators/README.md"]).lower()
    assert materialized.components["mutate"]["name"] == "hyperagents"


def test_script_binding_does_not_copy_a_stage_helper_bundle(tmp_path) -> None:
    script = tmp_path / "select.py"
    script.write_text("print('selected')\n")
    source = script.read_bytes()
    binding = ResolvedOperator(
        stage="select",
        source_kind="script",
        source=script,
        name=None,
        timeout_s=10.0,
        config={},
        portable=False,
        digest=hashlib.sha256(source).hexdigest(),
    )

    materialized = materialize_operators({"select": binding})

    assert "operators/select.py" in materialized.files
    assert not any(path.startswith("library/select/") for path in materialized.files)


def test_named_analyze_with_script_mutate_imports_from_root_shared_helpers(tmp_path) -> None:
    script = tmp_path / "custom_mutate.py"
    script.write_text(
        '"""Standalone custom mutate operator."""\n\n'
        "from evolve.frozen import sdk\n"
        "from evolve.frozen.config import Config\n"
        "from evolve.frozen.interfaces import MutateOperator, MutateResult\n"
        "\nCONFIG = Config({})\n\n"
        "class CustomMutate(MutateOperator):\n"
        "    def mutate(self, checkout, observation, ctx):\n"
        "        return MutateResult(changed=[], notes=[], usage={'usd': 0})\n\n"
        "if __name__ == '__main__':\n"
        "    sdk.main(CustomMutate, config_schema=CONFIG)\n"
    )
    recipe = tmp_path / "recipe"
    recipe.mkdir()
    config = load_config(ROOT / "recipes" / "ahe" / "evolve.yaml")
    config["operators"]["mutate"] = {
        "script": str(script),
        "timeout_s": 10,
        "config": {},
    }
    (recipe / "evolve.yaml").write_text(render_yaml(config))
    resolved = resolve_recipe(recipe)
    assert resolved.operators["mutate"].source_kind == "script"

    materialized = materialize_operators(resolved.operators)
    for relative, content in materialized.files.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            destination.write_bytes(content)
        else:
            destination.write_text(content)

    assert not any(path.startswith("library/mutate/") for path in materialized.files)
    for stage in ("mutate", "analyze"):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import runpy, sys; sys.argv = [sys.argv[1], '--describe']; "
                "runpy.run_path(sys.argv[0], run_name='__main__')",
                str(tmp_path / f"operators/{stage}.py"),
            ],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_materialization_supports_packaged_traversables(tmp_path) -> None:
    archive = tmp_path / "library.zip"
    source = b'"""Packaged selection."""\nfrom library._methods_shared.gepa import MARKER\n'
    helper = b"\x89PNG\r\n\x1a\n\x00\xff"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("library/__init__.py", '"""Closed library."""\n')
        package.writestr("library/_shared/helper.py", "SHARED = True\n")
        package.writestr("library/_methods_shared/__init__.py", "")
        package.writestr("library/_methods_shared/gepa/__init__.py", "MARKER = True\n")
        package.writestr("library/_methods_shared/unselected/__init__.py", "UNSELECTED = True\n")
        package.writestr("library/select/greedy.py", source)
        package.writestr("library/select/_support/payload.bin", helper)
    library = zipfile.Path(archive) / "library"
    binding = ResolvedOperator(
        stage="select",
        source_kind="library",
        source=library / "select" / "greedy.py",
        name="greedy",
        timeout_s=10.0,
        config={},
        portable=True,
        digest=hashlib.sha256(source).hexdigest(),
    )

    materialized = materialize_operators({"select": binding}, library=library)

    assert materialized.files["library/__init__.py"] == b'"""Closed library."""\n'
    assert materialized.files["library/_shared/helper.py"] == "SHARED = True\n"
    assert materialized.files["library/_methods_shared/gepa/__init__.py"] == "MARKER = True\n"
    assert "library/_methods_shared/unselected/__init__.py" not in materialized.files
    assert materialized.files["library/select/_support/payload.bin"] == helper


def test_materialization_rejects_symlinked_helper_assets(tmp_path) -> None:
    library = tmp_path / "library"
    source = library / "select" / "greedy.py"
    source.parent.mkdir(parents=True)
    source.write_text('"""Selected parent."""\n')
    (library / "__init__.py").write_text('"""Closed library."""\n')
    external = tmp_path / "external.py"
    external.write_text("EXTERNAL = True\n")
    (library / "select" / "_support.py").symlink_to(external)
    binding = ResolvedOperator(
        stage="select",
        source_kind="library",
        source=source,
        name="greedy",
        timeout_s=10.0,
        config={},
        portable=True,
        digest=hashlib.sha256(source.read_bytes()).hexdigest(),
    )

    with pytest.raises(ValueError, match="operator asset may not be a symlink"):
        materialize_operators({"select": binding}, library=library)


def test_script_materialization_rejects_symlinked_library_root(tmp_path: Path) -> None:
    external = tmp_path / "external"
    (external / "_shared").mkdir(parents=True)
    (external / "_shared" / "unexpected.py").write_text("UNEXPECTED = True\n")
    library = tmp_path / "library"
    library.symlink_to(external, target_is_directory=True)
    script = tmp_path / "select.py"
    script.write_text("print('selected')\n")
    source = script.read_bytes()
    binding = ResolvedOperator(
        stage="select",
        source_kind="script",
        source=script,
        name=None,
        timeout_s=10.0,
        config={},
        portable=False,
        digest=hashlib.sha256(source).hexdigest(),
    )

    with pytest.raises(ValueError, match=r"symlink.*library"):
        materialize_operators({"select": binding}, library=library)


def test_materialized_gepa_validate_imports_only_shared_harbor_runtime(tmp_path) -> None:
    materialized = materialize_operators(resolve_builtin_recipe("gepa").operators)
    assert "library/rollout/harbor.py" not in materialized.files
    assert "library/_methods_shared/gepa/__init__.py" in materialized.files
    assert "library/_shared/gepa.py" not in materialized.files
    for relative, content in materialized.files.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            destination.write_bytes(content)
        else:
            destination.write_text(content)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runpy, sys; sys.argv = [sys.argv[1], '--describe']; "
            "runpy.run_path(sys.argv[0], run_name='__main__')",
            str(tmp_path / "operators/validate.py"),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "library/_shared/harbor/__init__.py" in materialized.files
    assert "library/_shared/harbor/config.py" in materialized.files
    assert "library/_shared/harbor/evidence.py" in materialized.files
    assert "library/_shared/harbor/execution.py" in materialized.files
    assert "library/_shared/harbor/rollout.py" in materialized.files
    assert "library/_shared/harbor.py" not in materialized.files
