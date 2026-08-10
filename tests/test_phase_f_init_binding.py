from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_real_recipe_binds_harbor_rollout_analyze_and_hyperagents_mutate(tmp_path: Path) -> None:
    from evolve import workspace as workspace_module

    config = workspace_module.default_config("hill_climb", "hill")

    bindings = workspace_module._operator_bindings(config, recipe="hill_climb", init_cwd=tmp_path)
    rollout = next(binding for binding in bindings if binding.kind == "rollout")
    analyze = next(binding for binding in bindings if binding.kind == "analyze")
    mutate = next(binding for binding in bindings if binding.kind == "mutate")

    assert rollout.source == "library/rollout/harbor.py"
    assert '"target": "/opt/evolve/uv/cache"' in rollout.text
    assert '"target": "/installed-agent/uv-cache"' not in rollout.text
    assert analyze.source == "library/analyze/failure_patterns.py"
    expected_source = (ROOT / "library" / "mutate" / "hyperagents.py").read_text()
    assert mutate.source == "library/mutate/hyperagents.py"
    assert mutate.text == expected_source

    palette = workspace_module._operator_palette("hill_climb")
    assets = workspace_module._operator_assets("hill_climb")
    assert "library/mutate/_runners/__init__.py" in assets
    assert "library/mutate/_runners/local.py" in assets
    assert "library/mutate/_runners/harbor.py" in assets
    assert "library/mutate/_support/evidence.py" in assets
    assert "library/mutate/fixed.py" not in palette
    assert "library/mutate/noop.py" not in palette
    assert "library/mutate/llm.py" not in palette


def test_mutate_runners_are_not_operator_variants(tmp_path: Path) -> None:
    from evolve import workspace as workspace_module

    variants = workspace_module._available_operator_variants("hill_climb", "mutate")
    assert variants == ["aevolve", "ahe", "gepa", "hyperagents"]
    assert "local" not in variants
    assert "harbor" not in variants

    config = workspace_module.default_config("hill_climb", "hill")
    config["operators"]["mutate"]["variant"] = "harbor"
    try:
        workspace_module._operator_bindings(config, recipe="hill_climb", init_cwd=tmp_path)
    except ValueError as exc:
        assert "unknown mutate variant: harbor" in str(exc)
    else:
        raise AssertionError("expected runner-as-variant rejection")


def test_variant_markdown_companion_becomes_active_operator_prompt(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    library = tmp_path / "library"
    (library / "mutate").mkdir(parents=True)
    (library / "mutate" / "custom.py").write_text("# custom operator\n")
    (library / "mutate" / "custom.md").write_text("CUSTOM STRATEGY\n")
    monkeypatch.setattr(workspace_module, "library_root", lambda: library)

    config = {
        "operators": {
            "select": {"script": str(tmp_path / "select.py")},
            "rollout": {"script": str(tmp_path / "rollout.py")},
            "mutate": {"variant": "custom"},
            "gate": {"script": str(tmp_path / "gate.py")},
            "record": {"script": str(tmp_path / "record.py")},
        }
    }
    for name in ("select", "rollout", "gate", "record"):
        (tmp_path / f"{name}.py").write_text(f"# {name}\n")
    binding = next(
        item
        for item in workspace_module._operator_bindings(config, recipe="test", init_cwd=tmp_path)
        if item.kind == "mutate"
    )

    assert binding.companion_text == "CUSTOM STRATEGY\n"


def test_operator_assets_vendor_nested_prompt_files(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    library = tmp_path / "library"
    (library / "mutate" / "prompts").mkdir(parents=True)
    (library / "mutate" / "prompts" / "strategy.md").write_text("Strategy prompt\n")
    (library / "mutate" / "_runners").mkdir()
    (library / "mutate" / "_runners" / "backend.py").write_text("RUNNER = True\n")
    (library / "mutate" / "prompts" / "strategy.bin").write_bytes(b"\x86\x00")
    (library / "mutate" / "__pycache__").mkdir()
    (library / "mutate" / "__pycache__" / "strategy.cpython-314.pyc").write_bytes(b"\x86\x00")
    monkeypatch.setattr(workspace_module, "library_root", lambda: library)

    assets = workspace_module._operator_assets("custom")

    assert assets == {
        "library/mutate/prompts/strategy.md": "Strategy prompt\n",
        "library/mutate/_runners/backend.py": "RUNNER = True\n",
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
