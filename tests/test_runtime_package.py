from importlib import import_module, util

import evolve.runtime as runtime


def test_runtime_package_exposes_focused_modules_and_public_process_api() -> None:
    for name in ("auth", "config", "environment", "process"):
        assert import_module(f"evolve.runtime.{name}")
    assert runtime.OwnedResult.__module__ == "evolve.runtime.process"
    assert callable(runtime.run_owned)
    assert callable(runtime.attempt_dir)


def test_former_internal_runtime_import_paths_are_not_available() -> None:
    for name in ("runtime_auth", "runtime_config", "runtime_environment"):
        assert util.find_spec(f"evolve.{name}") is None
