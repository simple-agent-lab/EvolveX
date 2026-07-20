import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import write_locked_miniswe_seed

from evolve.uv_runtime import candidate_runtime_config


def test_uv_runtime_config_resolves_project_inside_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "target").mkdir(parents=True)

    config = candidate_runtime_config(
        checkout,
        {"candidate_runtime": {"variant": "uv", "project": "target"}},
    )

    assert config is not None
    assert config.variant == "uv"
    assert config.project == (checkout / "target").resolve()
    assert config.project_relative == "target"


@pytest.mark.parametrize(
    "value, message",
    [
        ("target", "candidate_runtime must be a mapping"),
        ({"variant": "pip", "project": "target"}, "unsupported candidate runtime variant"),
        ({"variant": "uv", "project": "../outside"}, "candidate runtime project escapes checkout"),
        ({"variant": "uv", "project": "/tmp/outside"}, "candidate runtime project must be relative"),
    ],
)
def test_uv_runtime_config_rejects_invalid_or_escaping_paths(
    tmp_path: Path, value: object, message: str
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    with pytest.raises(ValueError, match=message):
        candidate_runtime_config(checkout, {"candidate_runtime": value})


def test_missing_runtime_config_disables_preparation(tmp_path: Path) -> None:
    assert candidate_runtime_config(tmp_path, {}) is None


def test_frozen_project_can_rematerialize_offline_from_warm_cache(tmp_path: Path) -> None:
    project = write_locked_miniswe_seed(tmp_path / "project")
    cache = tmp_path / "uv-cache"
    env = {**os.environ, "UV_CACHE_DIR": str(cache)}
    command = [
        "uv",
        "sync",
        "--project",
        str(project),
        "--frozen",
        "--no-install-project",
        "--python",
        sys.executable,
    ]

    warm = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
    assert warm.returncode == 0, warm.stderr
    shutil.rmtree(project / ".venv")
    offline = subprocess.run([*command, "--offline"], env=env, text=True, capture_output=True, check=False)

    assert offline.returncode == 0, offline.stderr
    assert (project / ".venv" / "bin" / "python").is_file()
