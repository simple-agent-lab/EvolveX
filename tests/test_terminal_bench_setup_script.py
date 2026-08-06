from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "setup_terminal_bench.sh"

FAKE_TOOL = r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

name = Path(sys.argv[0]).name
args = sys.argv[1:]
log = Path(os.environ["SETUP_CALLS"])
with log.open("a") as stream:
    stream.write(json.dumps([name, *args]) + "\n")

if name == "docker":
    state = Path(os.environ["DOCKER_STATE"])
    images = set(state.read_text().splitlines()) if state.exists() else set()
    if args == ["info"]:
        raise SystemExit(12 if os.environ.get("FAIL_DOCKER_INFO") == "1" else 0)
    if args[:2] == ["image", "inspect"]:
        raise SystemExit(0 if args[2] in images else 1)
    if args[:1] == ["build"]:
        image = args[args.index("-t") + 1]
        images.add(image)
        state.write_text("\n".join(sorted(images)) + "\n")
        raise SystemExit(0)
    raise SystemExit(2)

if name == "uv":
    if args[:2] == ["sync", "--frozen"]:
        raise SystemExit(0)
    command = args[2:] if args[:2] == ["run", "--frozen"] else []
    if command[:2] == ["harbor", "download"]:
        output = Path(command[command.index("-o") + 1])
        (output / "terminal-bench").mkdir(parents=True)
        if os.environ.get("FAIL_DOWNLOAD") == "1":
            raise SystemExit(9)
        raise SystemExit(0)
    if command[:1] == ["python"]:
        destination = Path(command[-1])
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "dataset-source.json").write_text("{}\n")
        raise SystemExit(0)
    raise SystemExit(2)

if name == "git":
    raise SystemExit(0)
raise SystemExit(2)
'''


def _environment(tmp_path: Path, **values: str) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    tool = fake_bin / "tool"
    tool.write_text(FAKE_TOOL)
    tool.chmod(0o755)
    for name in ("docker", "git", "uv"):
        (fake_bin / name).symlink_to(tool)
    calls = tmp_path / "calls.jsonl"
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
            "EVOLVE_ASSET_DIR": str(tmp_path / "assets"),
            "SETUP_CALLS": str(calls),
            "DOCKER_STATE": str(tmp_path / "docker-images"),
            **values,
        }
    )
    return environment, calls


def _calls(path: Path) -> list[list[str]]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _run(tmp_path: Path, recipe: str, **values: str) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    environment, calls = _environment(tmp_path, **values)
    result = subprocess.run(
        ["bash", str(SCRIPT), recipe], cwd=ROOT, env=environment, text=True, capture_output=True, check=False
    )
    return result, _calls(calls)


def test_setup_rejects_recipes_outside_the_main_terminal_bench_set(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "gepa_local")

    assert result.returncode != 0
    assert "supported recipes" in result.stderr
    assert calls == []


def test_setup_stops_before_download_when_docker_is_unavailable(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "ahe", FAIL_DOCKER_INFO="1")

    assert result.returncode != 0
    assert "Docker daemon" in result.stderr
    assert calls == [["docker", "info"]]


def test_setup_downloads_once_and_builds_miniswe_image_for_ahe(tmp_path: Path) -> None:
    environment, calls_path = _environment(tmp_path)

    first = subprocess.run(
        ["bash", str(SCRIPT), "ahe"], cwd=ROOT, env=environment, text=True, capture_output=True, check=False
    )
    second = subprocess.run(
        ["bash", str(SCRIPT), "ahe"], cwd=ROOT, env=environment, text=True, capture_output=True, check=False
    )
    calls = _calls(calls_path)

    assert first.returncode == second.returncode == 0
    assert sum(call[0:5] == ["uv", "run", "--frozen", "harbor", "download"] for call in calls) == 1
    builds = [call for call in calls if call[:2] == ["docker", "build"]]
    assert len(builds) == 1
    assert "evolve-meta-agent-app:20260724-tools-mswe245" in builds[0]
    assert "./scripts/run_recipe_demo.sh ahe" in second.stdout


def test_setup_builds_codex_image_for_gepa(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "gepa")

    assert result.returncode == 0, result.stderr
    build = next(call for call in calls if call[:2] == ["docker", "build"])
    assert "evolve-meta-agent-codex:20260805-codex0145" in build


def test_setup_propagates_download_failure_without_building(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "hyperagents", FAIL_DOWNLOAD="1")

    assert result.returncode == 9
    assert not any(call[:2] == ["docker", "build"] for call in calls)
    assert not (tmp_path / "assets" / "raw" / "terminal-bench").exists()


def test_setup_script_is_portable_bash() -> None:
    assert shutil.which("bash")
    result = subprocess.run(["bash", "-n", str(SCRIPT)], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert sys.platform in {"darwin", "linux"}
