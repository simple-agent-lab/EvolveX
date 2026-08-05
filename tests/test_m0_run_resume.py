import os
from pathlib import Path

import pytest
from conftest import allow_local_runtime, git, init_workspace, run_evolve
from typer.testing import CliRunner

from evolve import cli
from evolve.archive import merged_rows as mechanism_merged_rows


def test_preflight_cli_prints_receipt_and_returns_zero(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allow_local_runtime(monkeypatch)

    result = CliRunner().invoke(cli.app, ["preflight", str(strict_workspace)])

    assert result.exit_code == 0, result.output
    assert "preflight: passed" in result.stdout
    assert "preflight.json" in result.stdout


@pytest.mark.parametrize(
    ("arguments", "exit_code"),
    [([], 1), (["--smoke"], 2)],
)
def test_preflight_cli_uses_distinct_failure_codes(
    strict_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    exit_code: int,
) -> None:
    allow_local_runtime(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = CliRunner().invoke(
        cli.app,
        ["preflight", str(strict_workspace), *arguments],
    )

    assert result.exit_code == exit_code
    assert "preflight: failed" in result.stdout
    assert "preflight.json" in result.stdout


def assert_complete_lineage(
    workspace: Path,
    max_gen: int,
    *,
    require_valid_parents: bool = True,
) -> list[dict[str, object]]:
    rows = mechanism_merged_rows(workspace / "archive.jsonl")
    assert [row["genid"] for row in rows] == [str(gen) for gen in range(max_gen + 1)]
    assert all(row["status"] == "complete" for row in rows)
    if require_valid_parents:
        assert all(row["valid_parent"] is True for row in rows)
    for gen in range(max_gen + 1):
        assert git(workspace, "tag", "--list", f"gen/{gen}") == f"gen/{gen}"
        assert git(workspace, "rev-parse", f"gen/{gen}^{{commit}}")
    return rows


def test_stub_run_produces_lineage_and_mirror(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    rows = assert_complete_lineage(workspace, 1)
    assert all(row["mutated"] == ["target/agent.py"] for row in rows[1:])
    assert git(workspace, "status", "--short").splitlines() == []
    assert git(workspace, "ls-files", "archive.jsonl") == ""

    mirror = evolve_home / "mirrors" / "experiment" / "archive.jsonl"
    mirror_rows = mechanism_merged_rows(mirror)
    assert [row["genid"] for row in mirror_rows] == ["0", "1"]
    assert mirror.read_text() == (workspace / "archive.jsonl").read_text()


def test_run_loads_workspace_dotenv_without_overriding_explicit_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".env").write_text("OPENAI_BASE_URL=https://dotenv.example/v1\nOPENAI_API_KEY=dotenv-key\n")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "explicit-key")
    captured: dict[str, str | None] = {}

    def fake_run(_options) -> None:
        captured["base_url"] = os.environ.get("OPENAI_BASE_URL")
        captured["api_key"] = os.environ.get("OPENAI_API_KEY")

    monkeypatch.setattr(cli, "driver_run", fake_run)

    cli.run(workspace, max_generations=0)

    assert captured == {
        "base_url": "https://dotenv.example/v1",
        "api_key": "explicit-key",
    }
    assert os.environ.get("OPENAI_BASE_URL") is None
    assert os.environ["OPENAI_API_KEY"] == "explicit-key"


def test_run_does_not_load_caller_dotenv_for_separate_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    caller = tmp_path / "framework"
    caller.mkdir()
    (caller / ".env").write_text("OPENAI_BASE_URL=https://caller.example/v1\n")
    workspace = tmp_path / "experiment"
    workspace.mkdir()
    monkeypatch.chdir(caller)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    captured: dict[str, str | None] = {}

    def fake_run(_options) -> None:
        captured["base_url"] = os.environ.get("OPENAI_BASE_URL")

    monkeypatch.setattr(cli, "driver_run", fake_run)

    cli.run(workspace, max_generations=0)

    assert captured["base_url"] is None
