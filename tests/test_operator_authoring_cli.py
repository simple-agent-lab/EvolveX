import json
from pathlib import Path

import pytest
from conftest import init_workspace, run_evolve
from typer.testing import CliRunner

from evolve import operator_cli
from evolve.cli import app

runner = CliRunner()


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
    library = tmp_path / "library"
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
    library = tmp_path / "library"
    monkeypatch.setattr(operator_cli, "library_root", lambda: library)

    result = runner.invoke(app, ["operator", "new", stage, "sample"])

    assert result.exit_code == 0, result.output
    assert expected in (library / stage / "sample.py").read_text()


def test_operator_new_refuses_to_overwrite_existing_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = tmp_path / "library"
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


def test_operator_active_replaces_workspace_oriented_list(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)

    listed = run_evolve("operator", "list", str(workspace), "--json")
    active = run_evolve("operator", "active", str(workspace), "--json")

    assert listed.returncode == 1
    assert active.returncode == 0, active.stderr
    entries = {entry["name"]: entry for entry in json.loads(active.stdout)}
    assert entries["select"]["operator"] == "greedy"
    assert "variant" not in entries["select"]


def test_operator_active_uses_frozen_component_provenance(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    config_path = workspace / "evolve.yaml"
    config_path.write_text(config_path.read_text().replace("operator: greedy", "operator: stale"))

    result = run_evolve("operator", "active", str(workspace), "--json")

    assert result.returncode == 0, result.stderr
    entries = {entry["name"]: entry for entry in json.loads(result.stdout)}
    assert entries["select"]["operator"] == "greedy"
