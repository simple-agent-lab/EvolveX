from pathlib import Path

from conftest import run_evolve

from evolve import __version__

ROOT = Path(__file__).resolve().parents[1]


def _provenance_and_body(bound_source: str) -> tuple[str, str]:
    header, body = bound_source.split("\n\n", 1)
    assert header.startswith("# evolve-provenance:")
    return header, body


def test_init_binds_dgm_select_to_score_weighted_library_variant_and_stamps_protocol(tmp_path: Path) -> None:
    workspace = tmp_path / "dgm-workspace"

    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "dgm-smoke",
        env={"EVOLVE_HOME": str(tmp_path / "home")},
    )

    assert result.returncode == 0, result.stderr
    expected_source = (ROOT / "library" / "select" / "score_weighted.py").read_text()
    header, body = _provenance_and_body((workspace / "operators" / "select.py").read_text())
    assert "kind=select" in header
    assert "source=library/select/score_weighted.py" in header
    assert f"framework_version={__version__}" in header
    assert "this file is yours now" in header
    assert "mechanism will never overwrite it" in header
    assert "evolve it" in header
    assert body == expected_source
    assert (workspace / ".evolve-protocol-version").read_text() == "1\n"


def test_ahe_latest_selector_is_available_as_a_library_variant() -> None:
    from evolve import workspace as workspace_module

    palette = workspace_module._operator_palette("ahe")

    assert "library/select/ahe_latest.py" in palette


def test_real_recipe_binds_meta_agent_to_agent_command_library_variant(tmp_path: Path) -> None:
    from evolve import workspace as workspace_module

    config = workspace_module.default_config("hill_climb", "hill")

    bindings = workspace_module._operator_bindings(config, recipe="hill_climb", init_cwd=tmp_path)
    meta_agent = next(binding for binding in bindings if binding.kind == "meta_agent")

    expected_source = (ROOT / "library" / "meta_agent" / "agent_command.py").read_text()
    assert meta_agent.source == "library/meta_agent/agent_command.py"
    assert meta_agent.text == expected_source

    palette = workspace_module._operator_palette("hill_climb")
    assert "library/meta_agent/agent_command.py" in palette
    assert "library/meta_agent/fixed.py" not in palette
    assert "library/meta_agent/noop.py" not in palette
    assert "library/meta_agent/llm.py" not in palette


def test_operator_assets_vendor_nested_prompt_files(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    library = tmp_path / "library"
    (library / "meta_agent" / "prompts").mkdir(parents=True)
    (library / "meta_agent" / "prompts" / "ahe.md").write_text("AHE prompt\n")
    (library / "meta_agent" / "prompts" / "ahe.bin").write_bytes(b"\x86\x00")
    (library / "meta_agent" / "__pycache__").mkdir()
    (library / "meta_agent" / "__pycache__" / "ahe.cpython-314.pyc").write_bytes(b"\x86\x00")
    monkeypatch.setattr(workspace_module, "library_root", lambda: library)

    assets = workspace_module._operator_assets("ahe")

    assert assets == {"library/meta_agent/prompts/ahe.md": "AHE prompt\n"}


def test_recipe_evaluator_assets_copy_training_but_not_sealed_files(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    recipes = tmp_path / "recipes"
    (recipes / "ahe" / "evaluator" / "tasks").mkdir(parents=True)
    (recipes / "ahe" / "evaluator" / "tasks" / "train-30.txt").write_text("task-a\n")
    (recipes / "ahe" / "sealed").mkdir()
    (recipes / "ahe" / "sealed" / "test-30.txt").write_text("secret-task\n")
    monkeypatch.setattr(workspace_module, "recipe_root", lambda: recipes)

    assert workspace_module._recipe_evaluator_assets("ahe") == {"evaluator/tasks/train-30.txt": "task-a\n"}
