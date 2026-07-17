from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_real_recipe_binds_harbor_rollout_trace_analyzer_and_hyperagents_meta_agent(tmp_path: Path) -> None:
    from evolve import workspace as workspace_module

    config = workspace_module.default_config("hill_climb", "hill")

    bindings = workspace_module._operator_bindings(config, recipe="hill_climb", init_cwd=tmp_path)
    rollout = next(binding for binding in bindings if binding.kind == "rollout")
    trace_analyzer = next(binding for binding in bindings if binding.kind == "trace_analyzer")
    meta_agent = next(binding for binding in bindings if binding.kind == "meta_agent")

    assert rollout.source == "library/rollout/harbor.py"
    assert trace_analyzer.source == "library/trace_analyzer/failure_patterns.py"
    expected_source = (ROOT / "library" / "meta_agent" / "hyperagents.py").read_text()
    assert meta_agent.source == "library/meta_agent/hyperagents.py"
    assert meta_agent.text == expected_source

    palette = workspace_module._operator_palette("hill_climb")
    assets = workspace_module._operator_assets("hill_climb")
    assert "library/meta_agent/runners/__init__.py" in assets
    assert "library/meta_agent/runners/local.py" in assets
    assert "library/meta_agent/runners/harbor.py" in assets
    assert "library/meta_agent/support/evidence.py" in assets
    assert "library/meta_agent/fixed.py" not in palette
    assert "library/meta_agent/noop.py" not in palette
    assert "library/meta_agent/llm.py" not in palette


def test_meta_agent_runners_are_not_operator_variants(tmp_path: Path) -> None:
    from evolve import workspace as workspace_module

    variants = workspace_module._available_operator_variants("hill_climb", "meta_agent")
    assert variants == ["hyperagents"]
    assert "local" not in variants
    assert "harbor" not in variants

    config = workspace_module.default_config("hill_climb", "hill")
    config["operators"]["meta_agent"]["variant"] = "harbor"
    try:
        workspace_module._operator_bindings(config, recipe="hill_climb", init_cwd=tmp_path)
    except ValueError as exc:
        assert "unknown meta_agent variant: harbor" in str(exc)
    else:
        raise AssertionError("expected runner-as-variant rejection")


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
    (library / "meta_agent" / "prompts" / "strategy.md").write_text("Strategy prompt\n")
    (library / "meta_agent" / "runners").mkdir()
    (library / "meta_agent" / "runners" / "backend.py").write_text("RUNNER = True\n")
    (library / "meta_agent" / "prompts" / "strategy.bin").write_bytes(b"\x86\x00")
    (library / "meta_agent" / "__pycache__").mkdir()
    (library / "meta_agent" / "__pycache__" / "strategy.cpython-314.pyc").write_bytes(b"\x86\x00")
    monkeypatch.setattr(workspace_module, "library_root", lambda: library)

    assets = workspace_module._operator_assets("custom")

    assert assets == {
        "library/meta_agent/prompts/strategy.md": "Strategy prompt\n",
        "library/meta_agent/runners/backend.py": "RUNNER = True\n",
    }


def test_operator_assets_reads_only_direct_root_python_helpers(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    library = tmp_path / "library"
    library.mkdir()
    helper = library / "shared_support.py"
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

    assets = workspace_module._operator_assets("custom")

    assert assets == {"library/shared_support.py": "ROOT_HELPER = True\n"}


def test_recipe_evaluator_assets_copy_training_but_not_sealed_files(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    recipes = tmp_path / "recipes"
    (recipes / "custom" / "evaluator" / "tasks").mkdir(parents=True)
    (recipes / "custom" / "evaluator" / "tasks" / "train.txt").write_text("task-a\n")
    (recipes / "custom" / "sealed").mkdir()
    (recipes / "custom" / "sealed" / "heldout.txt").write_text("secret-task\n")
    monkeypatch.setattr(workspace_module, "recipe_root", lambda: recipes)

    assert workspace_module._recipe_evaluator_assets("custom") == {"evaluator/tasks/train.txt": "task-a\n"}
