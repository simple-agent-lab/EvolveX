import json
from pathlib import Path

import pytest

from evolve.branching import (
    BranchIntent,
    branch_intent_path,
    consume_branch_intent,
    create_branch_intent,
    load_branch_intent,
)


def intent() -> BranchIntent:
    return BranchIntent(
        source_generation="4",
        source_tag="gen/4",
        source_commit="a" * 40,
        target_generation=11,
        target_genids=("11-0", "11-1"),
        created_at="2026-07-28T00:00:00+00:00",
    )


def test_branch_intent_round_trips_and_matching_create_is_idempotent(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"
    first = create_branch_intent(workspace, intent())
    second = create_branch_intent(workspace, intent())

    assert first == second == intent()
    assert load_branch_intent(workspace) == intent()


def test_branch_intent_refuses_conflicting_existing_intent(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"
    create_branch_intent(workspace, intent())
    conflicting = BranchIntent(**{**intent().__dict__, "source_generation": "3", "source_tag": "gen/3"})

    with pytest.raises(RuntimeError, match="conflicting branch intent"):
        create_branch_intent(workspace, conflicting)


def test_load_branch_intent_rejects_invalid_schema(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"
    path = branch_intent_path(workspace)
    path.parent.mkdir(parents=True)
    path.write_text('{"schema_version": 2}\n')

    with pytest.raises(RuntimeError, match="unsupported branch intent schema"):
        load_branch_intent(workspace)


def test_load_branch_intent_rejects_non_string_target_genid(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"
    path = branch_intent_path(workspace)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_generation": "4",
                "source_tag": "gen/4",
                "source_commit": "a" * 40,
                "target_generation": 11,
                "target_genids": ["11-0", 1],
                "created_at": "2026-07-28T00:00:00+00:00",
            }
        )
    )

    with pytest.raises(RuntimeError, match="invalid branch intent field target_genids"):
        load_branch_intent(workspace)


def test_consume_branch_intent_is_idempotent(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"
    current = create_branch_intent(workspace, intent())
    consume_branch_intent(workspace, current)
    consume_branch_intent(workspace, current)
    assert load_branch_intent(workspace) is None


def test_consume_branch_intent_refuses_replacement_and_preserves_it(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"
    current = create_branch_intent(workspace, intent())
    replacement = BranchIntent(**{**intent().__dict__, "target_generation": 12, "target_genids": ("12-0",)})
    path = branch_intent_path(workspace)
    path.write_text(json.dumps({"schema_version": 1, **replacement.__dict__, "target_genids": ["12-0"]}))

    with pytest.raises(RuntimeError, match="branch intent changed before it could be consumed"):
        consume_branch_intent(workspace, current)

    assert load_branch_intent(workspace) == replacement
