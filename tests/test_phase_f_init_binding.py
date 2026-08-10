from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_real_recipe_binds_harbor_rollout_analyze_and_hyperagents_mutate(tmp_path: Path) -> None:
    from evolve import workspace as workspace_module
    from evolve.recipe import resolve_builtin_recipe

    bindings = resolve_builtin_recipe("hill_climb").operators
    rollout = bindings["rollout"]
    analyze = bindings["analyze"]
    mutate = bindings["mutate"]

    assert rollout.name == "harbor"
    assert '"target": "/opt/evolve/uv/cache"' in rollout.source.read_text()
    assert '"target": "/installed-agent/uv-cache"' not in rollout.source.read_text()
    assert analyze.name == "failure_patterns"
    expected_source = (ROOT / "library" / "mutate" / "hyperagents.py").read_text()
    assert mutate.name == "hyperagents"
    assert mutate.source.read_text() == expected_source

    palette = workspace_module._operator_palette()
    assets = workspace_module._operator_assets()
    assert "library/mutate/_runners/__init__.py" in assets
    assert "library/mutate/_runners/local.py" in assets
    assert "library/mutate/_runners/harbor.py" in assets
    assert "library/mutate/_support/evidence.py" in assets
    assert "library/mutate/fixed.py" not in palette
    assert "library/mutate/noop.py" not in palette
    assert "library/mutate/llm.py" not in palette


def test_mutate_runners_are_not_operator_variants(tmp_path: Path) -> None:
    from evolve.operator_library import discover_operators

    variants = sorted(name for stage, name in discover_operators() if stage == "mutate")
    assert variants == ["aevolve", "ahe", "gepa", "hyperagents"]
    assert "local" not in variants
    assert "harbor" not in variants


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

    assets = workspace_module._operator_assets()

    assert assets == {
        "library/mutate/prompts/strategy.md": "Strategy prompt\n",
        "library/mutate/_runners/backend.py": "RUNNER = True\n",
    }


def test_operator_assets_reads_only_discovery_permitted_root_helpers(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    library = tmp_path / "library"
    library.mkdir()
    helper = library / "_shared_support.py"
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

    assets = workspace_module._operator_assets()

    assert assets == {"library/_shared_support.py": "ROOT_HELPER = True\n"}


def test_recipe_evaluator_assets_copy_training_but_not_sealed_files(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    recipes = tmp_path / "recipes"
    (recipes / "custom" / "evaluator" / "tasks").mkdir(parents=True)
    (recipes / "custom" / "evaluator" / "tasks" / "train.txt").write_text("task-a\n")
    (recipes / "custom" / "sealed").mkdir()
    (recipes / "custom" / "sealed" / "heldout.txt").write_text("secret-task\n")
    assert workspace_module._recipe_evaluator_assets(recipes / "custom") == {"evaluator/tasks/train.txt": "task-a\n"}
