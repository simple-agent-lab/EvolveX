import os
import shutil
import subprocess
import sys
from pathlib import Path

from conftest import write_locked_miniswe_seed


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
