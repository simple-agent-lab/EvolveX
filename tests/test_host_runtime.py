from __future__ import annotations

import os
import subprocess
import sys
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
        "TMPDIR": "/tmp/custom",
    }

    command, env = uv_run(tmp_path, "harbor", "run", env=source)

    assert command == [
        str(uv),
        "run",
        "--project",
        str(tmp_path.resolve()),
        "--frozen",
        "--python",
        sys.executable,
        "harbor",
        "run",
    ]
    assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} & env.keys()
    assert env["OPENAI_API_KEY"] == "secret"
    assert env["TMPDIR"] == "/tmp/custom"
    assert source["PYTHONPATH"] == "/unsafe"


def test_uv_executable_falls_back_to_path(tmp_path: Path) -> None:
    uv = _executable(tmp_path / "uv")

    assert uv_executable({"PATH": str(tmp_path)}) == str(uv)


def test_uv_run_does_not_redirect_temp_root_into_workspace(tmp_path: Path) -> None:
    _project(tmp_path)
    uv = _executable(tmp_path / "uv")

    _command, env = uv_run(tmp_path, "python", env={"EVOLVE_UV_BINARY": str(uv)})

    assert "TMPDIR" not in env
    assert not (tmp_path / "runs" / ".tmp").exists()


def test_uv_run_reuses_framework_python_with_empty_offline_uv_directories(tmp_path: Path) -> None:
    _project(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='test'\nversion='0'\nrequires-python='>=3.12'\n[tool.uv]\npackage=false\n"
    )
    (tmp_path / "uv.lock").unlink()
    locked = subprocess.run(
        [uv_executable(os.environ), "lock", "--project", str(tmp_path), "--python", sys.executable],
        text=True,
        capture_output=True,
        check=False,
    )
    assert locked.returncode == 0, locked.stderr
    home = tmp_path / "empty-home"
    cache = tmp_path / "empty-cache"
    python_dir = tmp_path / "empty-python"
    home.mkdir()
    cache.mkdir()
    python_dir.mkdir()
    command, env = uv_run(
        tmp_path,
        "python",
        "-c",
        "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
        env={
            **os.environ,
            "HOME": str(home),
            "UV_CACHE_DIR": str(cache),
            "UV_OFFLINE": "1",
            "UV_PYTHON_INSTALL_DIR": str(python_dir),
        },
    )

    result = subprocess.run(command, env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{sys.version_info.major}.{sys.version_info.minor}"
    assert not any(python_dir.iterdir())


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
