import json
import subprocess
from pathlib import Path

import pytest
from conftest import init_workspace, run_evolve
from typer.testing import CliRunner

from evolve import operator_cli
from evolve.cli import app
from evolve.operator_library import describe_operator, resolve_operator, validate_operator_config

runner = CliRunner()


def _source_checkout_library(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    (checkout / "pyproject.toml").write_text("[project]\nname = 'fixture'\nversion = '0'\n")
    (checkout / "src/evolve").mkdir(parents=True)
    library = checkout / "library"
    library.mkdir()
    (library / "__init__.py").write_text('"""Fixture operator library."""\n')
    shared = library / "_shared/config.py"
    shared.parent.mkdir()
    shared.write_bytes((Path(__file__).resolve().parents[1] / "library/_shared/config.py").read_bytes())
    return library


def test_operator_list_discovers_library_by_stage() -> None:
    result = run_evolve("operator", "list", "mutate", "--json")

    assert result.returncode == 0, result.stderr
    names = {entry["name"] for entry in json.loads(result.stdout)}
    assert {"aevolve", "ahe", "gepa", "hyperagents"} <= names


def test_operator_list_excludes_library_helpers() -> None:
    result = run_evolve("operator", "list", "--json")

    assert result.returncode == 0, result.stderr
    entries = json.loads(result.stdout)
    assert entries == sorted(entries, key=lambda entry: (entry["stage"], entry["name"]))
    assert not any(entry["name"].startswith("_") for entry in entries)
    assert not any(entry["name"] == "skeleton" for entry in entries)


def test_operator_describe_and_check_use_library_subprocess_protocol() -> None:
    described = run_evolve("operator", "describe", "mutate/aevolve", "--json")
    checked = run_evolve("operator", "check", "mutate/aevolve", "--config", "{}", "--json")

    assert described.returncode == 0, described.stderr
    assert json.loads(described.stdout)["identity"] == "mutate/aevolve"
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)["runner"] == "local"


@pytest.mark.parametrize("identity", ["mutate", "unknown/critic_editor", "mutate/bad-name", "mutate/gepa/extra"])
def test_operator_describe_rejects_invalid_identity(identity: str) -> None:
    result = run_evolve("operator", "describe", identity)

    assert result.returncode == 1
    assert result.stderr.startswith("evolve: ")


def test_operator_new_creates_one_valid_entry_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _source_checkout_library(tmp_path)
    monkeypatch.setattr(operator_cli, "library_root", lambda: library)

    result = runner.invoke(app, ["operator", "new", "mutate", "critic_editor"])

    assert result.exit_code == 0, result.output
    created = library / "mutate" / "critic_editor.py"
    assert created.is_file()
    assert "class CriticEditor(MutateOperator)" in created.read_text()
    assert "validate_config=validate_config" in created.read_text()


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("select", 'SelectResult(["0"]'),
        ("rollout", "RolloutResult({}, [])"),
        ("analyze", "AnalyzeResult({}, [])"),
        ("mutate", 'MutateResult(changed=[], notes=["sample made no changes"], usage={"usd": 0})'),
        ("validate", 'ValidateResult(True, "generated validation accepts", [])'),
        ("novelty", "NoveltyResult(1.0, True)"),
        ("gate", 'GateResult("reject", "generated gate requires policy")'),
        ("record", "RecordResult({})"),
        ("reflect", "ReflectResult([])"),
    ],
)
def test_operator_new_generates_a_valid_minimal_stage_operator(
    stage: str, expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _source_checkout_library(tmp_path)
    monkeypatch.setattr(operator_cli, "library_root", lambda: library)

    result = runner.invoke(app, ["operator", "new", stage, "sample"])

    assert result.exit_code == 0, result.output
    assert expected in (library / stage / "sample.py").read_text()


@pytest.mark.parametrize(
    "stage",
    ["select", "rollout", "analyze", "mutate", "validate", "novelty", "gate", "record", "reflect"],
)
def test_operator_new_scaffold_executes_describe_and_check_modes(
    stage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _source_checkout_library(tmp_path)
    monkeypatch.setattr(operator_cli, "library_root", lambda: library)

    created = runner.invoke(app, ["operator", "new", stage, "sample"])
    operator = resolve_operator(stage, "sample", library)

    assert created.exit_code == 0, created.output
    description = describe_operator(operator)
    assert description["config_validation"] is True
    assert description["stage"] == stage
    assert validate_operator_config(operator, {}) == {}


def test_operator_new_refuses_to_overwrite_existing_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = _source_checkout_library(tmp_path)
    target = library / "mutate" / "critic_editor.py"
    target.parent.mkdir(parents=True)
    target.write_text("existing\n")
    monkeypatch.setattr(operator_cli, "library_root", lambda: library)

    result = runner.invoke(app, ["operator", "new", "mutate", "critic_editor"])

    assert result.exit_code == 1
    assert target.read_text() == "existing\n"
    assert "already exists" in result.output


def test_operator_new_requires_a_source_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(operator_cli, "library_root", object)

    result = runner.invoke(app, ["operator", "new", "mutate", "critic_editor"])

    assert result.exit_code == 1
    assert "operator authoring requires a source checkout" in result.output


def test_operator_new_rejects_writable_unpacked_install_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "site-packages/evolve"
    library = package / "library"
    library.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    monkeypatch.setattr(operator_cli, "library_root", lambda: library)

    result = runner.invoke(app, ["operator", "new", "mutate", "critic_editor"])

    assert result.exit_code == 1
    assert "operator authoring requires a source checkout" in result.output
    assert not (library / "mutate/critic_editor.py").exists()


def test_operator_active_replaces_workspace_oriented_list(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)

    listed = run_evolve("operator", "list", str(workspace), "--json")
    active = run_evolve("operator", "active", str(workspace), "--json")

    assert listed.returncode == 1
    assert active.returncode == 0, active.stderr
    entries = {entry["name"]: entry for entry in json.loads(active.stdout)}
    assert entries["select"]["operator"] == "greedy"
    assert "variant" not in entries["select"]


@pytest.mark.parametrize("workspace_name", ["plain-directory", "missing-directory"])
def test_operator_active_rejects_a_path_that_is_not_an_initialized_workspace(
    tmp_path: Path, workspace_name: str
) -> None:
    workspace = tmp_path / workspace_name
    if workspace_name == "plain-directory":
        workspace.mkdir()

    result = run_evolve("operator", "active", str(workspace), "--json")

    assert result.returncode == 1
    assert result.stderr.startswith("evolve: operator active requires an initialized workspace:")


def test_operator_active_uses_frozen_component_provenance(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    config_path = workspace / "evolve.yaml"
    config_path.write_text(config_path.read_text().replace("operator: greedy", "operator: stale"))

    result = run_evolve("operator", "active", str(workspace), "--json")

    assert result.returncode == 0, result.stderr
    entries = {entry["name"]: entry for entry in json.loads(result.stdout)}
    assert entries["select"]["operator"] == "greedy"


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ("{", "--config must be valid JSON"),
        ("[]", "--config must be a JSON object"),
        ('{"value": NaN}', "--config must be valid JSON"),
    ],
)
def test_operator_check_invalid_config_uses_the_guarded_error_path(config: str, message: str) -> None:
    result = run_evolve("operator", "check", "mutate/aevolve", "--config", config)

    assert result.returncode == 1
    assert result.stderr.startswith(f"evolve: {message}")
    assert "Usage:" not in result.stderr


def test_operator_check_accepts_local_mutation_command() -> None:
    command = "printf command-accepted"

    result = run_evolve(
        "operator",
        "check",
        "mutate/hyperagents",
        "--config",
        json.dumps({"runner": "local", "command": command}),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["command"] == command
