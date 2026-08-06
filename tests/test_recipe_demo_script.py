import json
import os
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_recipe_demo.sh"

FAKE_UV = """\
#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

arguments = sys.argv[1:]
with Path(os.environ["UV_CALLS"]).open("a") as stream:
    stream.write(json.dumps(arguments) + "\\n")
if arguments[:2] != ["run", "--frozen"]:
    raise SystemExit(0)
command = arguments[2:]
if command[:1] == ["--env-file"]:
    for line in Path(command[1]).read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name, value = stripped.split("=", 1)
            os.environ.setdefault(name, value.strip("'\\\""))
    command = command[2:]
if command[:2] == ["sh", "-c"]:
    os.execvpe("sh", command, os.environ)
"""


def _fake_uv(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv = fake_bin / "uv"
    uv.write_text(textwrap.dedent(FAKE_UV))
    uv.chmod(0o755)
    return fake_bin, tmp_path / "uv-calls.jsonl"


def _environment(fake_bin: Path, calls: Path, **values: str) -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("DATASET", "ENV_FILE", "GENERATIONS", "OPENAI_API_KEY", "RECIPE", "SEED", "TASKS", "WORKSPACE"):
        environment.pop(name, None)
    environment.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
            "UV_CALLS": str(calls),
            **values,
        }
    )
    return environment


def _calls(path: Path) -> list[list[str]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_recipe_demo_routes_common_overrides_through_uv(tmp_path: Path) -> None:
    fake_bin, calls_path = _fake_uv(tmp_path)
    workspace = tmp_path / "workspace"

    subprocess.run(
        ["bash", str(SCRIPT), "gepa"],
        check=True,
        cwd=tmp_path,
        env=_environment(
            fake_bin,
            calls_path,
            OPENAI_API_KEY="demo-key",
            WORKSPACE=str(workspace),
            TASKS="4",
            GENERATIONS="2",
            DATASET="/datasets/gepa",
            SEED="/seeds/gepa",
        ),
    )

    calls = _calls(calls_path)
    assert calls[0] == ["sync", "--frozen"]
    assert calls[2] == [
        "run",
        "--frozen",
        "evolve",
        "init",
        str(workspace),
        "--recipe",
        "gepa",
        "--tasks",
        "4",
        "--dataset",
        "/datasets/gepa",
        "--seed",
        "/seeds/gepa",
    ]
    assert calls[3] == ["run", "--frozen", f"{workspace}/evolve", "preflight", str(workspace), "--smoke"]
    assert calls[4] == [
        "run",
        "--frozen",
        f"{workspace}/evolve",
        "run",
        str(workspace),
        "--max-generations",
        "2",
        "--children-per-gen",
        "1",
    ]
    assert all(call[:2] == ["run", "--frozen"] for call in calls[1:])


def test_recipe_demo_loads_default_ahe_key_from_env_file(tmp_path: Path) -> None:
    fake_bin, calls_path = _fake_uv(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=file-key\n")

    subprocess.run(
        ["bash", str(SCRIPT)],
        check=True,
        cwd=tmp_path,
        env=_environment(fake_bin, calls_path, ENV_FILE=str(env_file)),
    )

    calls = _calls(calls_path)
    assert calls[1][:4] == ["run", "--frozen", "--env-file", str(env_file)]
    assert calls[2] == [
        "run",
        "--frozen",
        "--env-file",
        str(env_file),
        "evolve",
        "init",
        "./runs/ahe-demo",
        "--recipe",
        "ahe",
        "--tasks",
        "3",
    ]


def test_recipe_demo_rejects_missing_api_key_before_init(tmp_path: Path) -> None:
    fake_bin, calls_path = _fake_uv(tmp_path)

    result = subprocess.run(
        ["bash", str(SCRIPT), "hill_climb"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=_environment(fake_bin, calls_path, ENV_FILE=str(tmp_path / "missing.env")),
    )

    assert result.returncode != 0
    assert "OPENAI_API_KEY" in result.stderr
    assert _calls(calls_path) == [
        ["sync", "--frozen"],
        ["run", "--frozen", "sh", "-c", ': "${OPENAI_API_KEY:?Set OPENAI_API_KEY in the environment or ENV_FILE}"'],
    ]


def test_recipe_demo_remains_short_portable_bash() -> None:
    result = subprocess.run(["bash", "-n", str(SCRIPT)], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    text = SCRIPT.read_text()
    for private in ("DevBox", "/data00", "proxy.env", "REPO_BUNDLE", "python -"):
        assert private not in text
    assert len(text.splitlines()) <= 30
