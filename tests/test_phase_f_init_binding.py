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


def test_ahe_smoke_init_binds_all_method_faithful_operator_sources(tmp_path: Path) -> None:
    from evolve import workspace as workspace_module

    config = workspace_module.default_config("ahe-smoke", "ahe")

    bindings = workspace_module._operator_bindings(config, recipe="ahe-smoke", init_cwd=tmp_path)

    assert {(binding.kind, binding.source) for binding in bindings} == {
        ("select", "library/select/ahe_latest.py"),
        ("rollout", "library/rollout/ahe_trace_analysis.py"),
        ("meta_agent", "library/meta_agent/ahe_evidence_editor.py"),
        ("gate", "library/gate/ahe_artifact_valid.py"),
        ("record", "library/record/ahe_manifest.py"),
    }
    assets = workspace_module._operator_assets("ahe")
    assert "library/meta_agent/prompts/ahe_evolve.md" in assets
    assert "library/rollout/prompts/ahe_debugger.md" in assets
    assert "library/rollout/prompts/ahe_debugger_overview.md" in assets


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


def test_variant_markdown_companion_becomes_active_operator_prompt(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    library = tmp_path / "library"
    (library / "meta_agent").mkdir(parents=True)
    (library / "meta_agent" / "custom.py").write_text("# custom operator\n")
    (library / "meta_agent" / "custom.md").write_text("CUSTOM STRATEGY\n")
    monkeypatch.setattr(workspace_module, "library_root", lambda: library)

    config = {
        "operators": {
            "select": {"script": str(tmp_path / "select.py")},
            "rollout": {"script": str(tmp_path / "rollout.py")},
            "meta_agent": {"variant": "custom"},
            "gate": {"script": str(tmp_path / "gate.py")},
            "record": {"script": str(tmp_path / "record.py")},
        }
    }
    for name in ("select", "rollout", "gate", "record"):
        (tmp_path / f"{name}.py").write_text(f"# {name}\n")
    binding = next(
        item
        for item in workspace_module._operator_bindings(config, recipe="test", init_cwd=tmp_path)
        if item.kind == "meta_agent"
    )

    assert binding.companion_text == "CUSTOM STRATEGY\n"


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


def test_operator_assets_reads_only_direct_root_python_helpers(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    library = tmp_path / "library"
    library.mkdir()
    helper = library / "ahe_support.py"
    helper.write_text("ROOT_HELPER = True\n")
    nested = library / "internal" / "credential_loader.py"
    nested.parent.mkdir()
    nested.write_text("MUST_NOT_BE_READ = True\n")
    original_read_text = Path.read_text

    def guarded_read_text(path: Path, *args, **kwargs):
        if path == nested:
            raise AssertionError("nested root helper candidate was read")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(workspace_module, "library_root", lambda: library)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    assets = workspace_module._operator_assets("ahe")

    assert assets == {"library/ahe_support.py": "ROOT_HELPER = True\n"}


def test_recipe_evaluator_assets_copy_training_but_not_sealed_files(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    recipes = tmp_path / "recipes"
    (recipes / "ahe" / "evaluator" / "tasks").mkdir(parents=True)
    (recipes / "ahe" / "evaluator" / "tasks" / "train-30.txt").write_text("task-a\n")
    (recipes / "ahe" / "sealed").mkdir()
    (recipes / "ahe" / "sealed" / "heldout.txt").write_text("secret-task\n")
    monkeypatch.setattr(workspace_module, "recipe_root", lambda: recipes)

    assert workspace_module._recipe_evaluator_assets("ahe") == {"evaluator/tasks/train-30.txt": "task-a\n"}
