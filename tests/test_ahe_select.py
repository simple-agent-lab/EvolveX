import importlib.util
import random
from pathlib import Path
from types import SimpleNamespace

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def test_ahe_latest_selects_newest_valid_parent_even_when_score_is_lower(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("ahe_latest_test", ROOT / "library/select/ahe_latest.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    archive = SimpleNamespace(
        valid_parents=lambda: [{"genid": "1", "score": 0.9}, {"genid": "2", "score": 0.1}]
    )
    ctx = OperatorContext(tmp_path, tmp_path, tmp_path, "3", "2", None, 1, {}, random.Random(0))
    assert module.AheLatestSelect().pick(archive, ctx).parents == ["2"]
