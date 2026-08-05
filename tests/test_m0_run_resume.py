import os
import shutil
from pathlib import Path

import pytest
from conftest import git, init_workspace, run_evolve

from evolve import cli
from evolve.archive import append_event, ensure_local_archive, eval_receipt_path, mirror_path
from evolve.archive import merged_rows as mechanism_merged_rows


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

    mirror = mirror_path("experiment", workspace)
    mirror_rows = mechanism_merged_rows(mirror)
    assert [row["genid"] for row in mirror_rows] == ["0", "1"]
    assert mirror.read_text() == (workspace / "archive.jsonl").read_text()


def test_same_experiment_id_uses_workspace_scoped_mirrors(tmp_path: Path) -> None:
    first = tmp_path / "first" / "experiment"
    second = tmp_path / "second" / "experiment"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    append_event(first, "shared-id", {"genid": "first"})
    append_event(second, "shared-id", {"genid": "second"})

    first_mirror = mirror_path("shared-id", first)
    second_mirror = mirror_path("shared-id", second)
    assert first_mirror != second_mirror
    assert [row["genid"] for row in mechanism_merged_rows(first_mirror)] == ["first"]
    assert [row["genid"] for row in mechanism_merged_rows(second_mirror)] == ["second"]


def test_legacy_unscoped_mirror_is_not_silently_attached_to_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    legacy = mirror_path("shared-id")
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"genid":"unknown-origin"}\n')

    with pytest.raises(RuntimeError, match="both archive.jsonl and .evolve-eval-receipts.jsonl"):
        ensure_local_archive(workspace, "shared-id")

    assert not (workspace / "archive.jsonl").exists()


def test_same_path_reinitialized_workspace_gets_a_new_mirror_identity(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    git(workspace, "init")
    append_event(workspace, "shared-id", {"genid": "old"})
    old_mirror = mirror_path("shared-id", workspace)

    shutil.rmtree(workspace)
    workspace.mkdir()
    git(workspace, "init")
    append_event(workspace, "shared-id", {"genid": "new"})
    new_mirror = mirror_path("shared-id", workspace)

    assert new_mirror != old_mirror
    assert [row["genid"] for row in mechanism_merged_rows(old_mirror)] == ["old"]
    assert [row["genid"] for row in mechanism_merged_rows(new_mirror)] == ["new"]
    assert [row["genid"] for row in mechanism_merged_rows(workspace / "archive.jsonl")] == ["new"]


def test_moved_workspace_recovers_from_the_same_persistent_mirror(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.mkdir()
    git(original, "init")
    append_event(original, "shared-id", {"genid": "1"})
    mirror = mirror_path("shared-id", original)

    moved = tmp_path / "moved"
    original.rename(moved)
    (moved / "archive.jsonl").unlink()
    ensure_local_archive(moved, "shared-id")

    assert mirror_path("shared-id", moved) == mirror
    assert [row["genid"] for row in mechanism_merged_rows(moved / "archive.jsonl")] == ["1"]


def test_orphaned_scoped_mirror_fails_closed_instead_of_starting_empty(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    orphan = Path(os.environ["EVOLVE_HOME"]) / "mirrors" / "shared-id" / "old-path-key" / "archive.jsonl"
    orphan.parent.mkdir(parents=True)
    orphan.write_text('{"genid":"old"}\n')

    with pytest.raises(RuntimeError, match="cannot be safely attributed"):
        ensure_local_archive(workspace, "shared-id")

    assert not (workspace / "archive.jsonl").exists()


def test_local_ledger_migrates_to_uuid_mirror_without_merging_legacy_history(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    local = workspace / "archive.jsonl"
    local.write_text('{"genid":"local"}\n')
    eval_receipt_path(local).write_text("local-receipt\n")
    legacy = mirror_path("shared-id")
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"genid":"conflicting"}\n')
    eval_receipt_path(legacy).write_text("conflicting-receipt\n")

    ensure_local_archive(workspace, "shared-id")

    scoped = mirror_path("shared-id", workspace)
    assert scoped.read_text() == local.read_text() == '{"genid":"local"}\n'
    assert eval_receipt_path(scoped).read_text() == "local-receipt\n"
    assert eval_receipt_path(local).read_text() == "local-receipt\n"


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
    monkeypatch.setattr(cli, "write_run_summary", lambda *_args, **_kwargs: ({"completed_through": None}, workspace))

    cli.run(workspace, max_generations=0, assert_success=False)

    assert captured == {
        "base_url": "https://dotenv.example/v1",
        "api_key": "explicit-key",
    }
    assert os.environ.get("OPENAI_BASE_URL") is None
    assert os.environ["OPENAI_API_KEY"] == "explicit-key"


def test_run_uses_caller_dotenv_as_fallback_for_separate_workspace(
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
    monkeypatch.setattr(cli, "write_run_summary", lambda *_args, **_kwargs: ({"completed_through": None}, workspace))

    cli.run(workspace, max_generations=0, assert_success=False)

    assert captured["base_url"] == "https://caller.example/v1"
