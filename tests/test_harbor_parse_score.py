import importlib.util
import json
import sys
from pathlib import Path

import pytest

from evolve.config import scaffold_root


def _load_parse_score():
    path = scaffold_root() / "evaluators" / "harbor" / "parse_score.py"
    spec = importlib.util.spec_from_file_location("harbor_parse_score", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_runtime_trial_limit_overrides_larger_selected_pool(tmp_path: Path, monkeypatch) -> None:
    parse_score = _load_parse_score()
    (tmp_path / "task-split.json").write_text(json.dumps({"tasks": [f"task-{i}" for i in range(50)]}))
    monkeypatch.setenv("EVOLVE_HARBOR_EXPECTED_TRIALS", "2")

    assert parse_score._expected_trials(
        tmp_path,
        {"EVOLVE_HARBOR_EXPECTED_TRIALS": "50", "EVOLVE_HARBOR_ATTEMPTS": "1"},
    ) == 2


def test_selected_pool_fallback_uses_persisted_attempt_count(tmp_path: Path, monkeypatch) -> None:
    parse_score = _load_parse_score()
    (tmp_path / "task-split.json").write_text(json.dumps({"tasks": ["one", "two", "three"]}))
    monkeypatch.delenv("EVOLVE_HARBOR_EXPECTED_TRIALS", raising=False)

    assert parse_score._expected_trials(
        tmp_path,
        {"EVOLVE_HARBOR_EXPECTED_TRIALS": "99", "EVOLVE_HARBOR_ATTEMPTS": "2"},
    ) == 6


@pytest.mark.parametrize(
    ("env_values", "expected"),
    [
        ({"EVOLVE_HARBOR_EXPECTED_TRIALS": "7", "EVOLVE_HARBOR_N": "9"}, 7),
        ({"EVOLVE_HARBOR_N": "9"}, 9),
    ],
)
def test_env_file_fallback_without_selected_pool(
    tmp_path: Path,
    monkeypatch,
    env_values: dict[str, str],
    expected: int,
) -> None:
    parse_score = _load_parse_score()
    monkeypatch.delenv("EVOLVE_HARBOR_EXPECTED_TRIALS", raising=False)

    assert parse_score._expected_trials(tmp_path, env_values) == expected
