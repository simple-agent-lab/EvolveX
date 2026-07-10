import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ahe_latest", ROOT / "library" / "select" / "ahe_latest.py")
assert SPEC is not None and SPEC.loader is not None
AHE_LATEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AHE_LATEST)


class FakeArchive:
    def __init__(self, parents: list[dict[str, object]]) -> None:
        self.parents = parents

    def valid_parents(self) -> list[dict[str, object]]:
        return self.parents


def test_pick_returns_exactly_newest_numeric_generation() -> None:
    result = AHE_LATEST.AheLatestSelect().pick(
        FakeArchive([{"genid": "9"}, {"genid": "10"}, {"genid": "2"}]),
        None,
    )

    assert result.parents == ["10"]


def test_pick_breaks_numeric_generation_tie_by_full_genid() -> None:
    result = AHE_LATEST.AheLatestSelect().pick(
        FakeArchive([{"genid": "12-a"}, {"genid": "12-z"}, {"genid": "11-zz"}]),
        None,
    )

    assert result.parents == ["12-z"]


def test_pick_exits_when_no_valid_ahe_parent_exists() -> None:
    with pytest.raises(SystemExit, match="no valid AHE parent"):
        AHE_LATEST.AheLatestSelect().pick(FakeArchive([]), None)
