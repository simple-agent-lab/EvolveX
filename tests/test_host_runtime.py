from __future__ import annotations

import os
from pathlib import Path

import pytest

from evolve.host_runtime import clean_python_env, uv_executable, uv_run


def _project(root: Path) -> None:
    (root / "pyproject.toml").write_text("[project]\nname='test'\nversion='0'\n")
    (root / "uv.lock").write_text("version = 1\n")


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_uv_run_uses_locked_workspace_and_cleans_python_environment(tmp_path: Path) -> None:
    _project(tmp_path)
    uv = _executable(tmp_path / "uv")
    source = {
        "EVOLVE_UV_BINARY": str(uv),
        "PYTHONPATH": "/unsafe",
        "PYTHONHOME": "/wrong",
        "VIRTUAL_ENV": "/other",
        "OPENAI_API_KEY": "secret",
    }

    command, env = uv_run(tmp_path, "harbor", "run", env=source)

    assert command == [str(uv), "run", "--project", str(tmp_path.resolve()), "--frozen", "harbor", "run"]
    assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} & env.keys()
    assert env["OPENAI_API_KEY"] == "secret"
    assert source["PYTHONPATH"] == "/unsafe"


def test_uv_executable_falls_back_to_path(tmp_path: Path) -> None:
    uv = _executable(tmp_path / "uv")

    assert uv_executable({"PATH": str(tmp_path)}) == str(uv)


def test_uv_run_reports_missing_runtime_inputs(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="workspace uv project is missing.*pyproject.toml"):
        uv_run(tmp_path, "python", env={"PATH": os.defpath})

    _project(tmp_path)
    with pytest.raises(RuntimeError, match="uv is required; install uv or set EVOLVE_UV_BINARY"):
        uv_run(tmp_path, "python", env={"PATH": ""})


def test_clean_python_env_does_not_mutate_parent_mapping() -> None:
    source = {"PYTHONPATH": "/unsafe", "KEEP": "yes"}

    clean = clean_python_env(source)

    assert clean == {"KEEP": "yes"}
    assert source == {"PYTHONPATH": "/unsafe", "KEEP": "yes"}
