from pathlib import Path

import pytest

from evolve import config as config_module
from evolve.config import CONFIG_SECTIONS, load_config, operator_blocks, render_yaml


def test_operator_blocks_parse_nested_operator_config(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "evolve.yaml").write_text(
        "experiment:\n"
        "  id: test\n"
        "operators:\n"
        "  meta_agent:\n"
        "    timeout_s: 1800\n"
        "    command: uv run --project /opt/miniswe python /opt/meta.py\n"
        "  timeout_s: 900\n"
    )

    operators = operator_blocks(workspace)

    assert operators["meta_agent"] == {
        "timeout_s": 1800,
        "command": "uv run --project /opt/miniswe python /opt/meta.py",
    }
    assert operators["timeout_s"] == 900


def test_operator_blocks_preserve_arbitrary_nested_yaml(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "evolve.yaml").write_text(
        "experiment:\n  id: test\n"
        "target: {}\n"
        "surface: {include: [target/**], exclude: []}\n"
        "operators:\n"
        "  rollout:\n"
        "    variant: custom_trace_analysis\n"
        "    controls:\n"
        "      successful: 3\n"
        "      labels: [stable, 'contains: colon']\n"
        "    analyze:\n"
        "      failures: true\n"
        "      thresholds: {partial: 0.5, retry: null}\n"
        "evaluator: {}\n"
    )

    assert operator_blocks(workspace)["rollout"] == {
        "variant": "custom_trace_analysis",
        "controls": {"successful": 3, "labels": ["stable", "contains: colon"]},
        "analyze": {"failures": True, "thresholds": {"partial": 0.5, "retry": None}},
    }


def test_render_yaml_round_trips_all_five_sections(tmp_path: Path) -> None:
    config = {section: {} for section in CONFIG_SECTIONS}
    config["operators"] = {"rollout": {"custom": {"list": [1, "two"], "flag": True}}}
    rendered = render_yaml(config)
    config_path = tmp_path / "evolve.yaml"
    config_path.write_text(rendered)
    assert load_config(config_path) == config


def test_render_yaml_preserves_nested_candidate_runtime(tmp_path: Path) -> None:
    config = {section: {} for section in CONFIG_SECTIONS}
    config["evaluator"] = {
        "engine": "harbor",
        "candidate_runtime": {"variant": "uv", "project": "target", "python": "3.12"},
        "max_retries": 1,
        "benchmark_timeout_is_zero": True,
    }
    config_path = tmp_path / "evolve.yaml"
    config_path.write_text(render_yaml(config))

    assert load_config(config_path)["evaluator"] == config["evaluator"]


def test_unknown_top_level_section_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "evolve.yaml").write_text("experiment: {}\nunsupported: {}\n")

    with pytest.raises(ValueError, match="unknown top-level config sections: unsupported"):
        operator_blocks(workspace)


@pytest.mark.parametrize(
    ("evaluator", "expected"),
    [
        ({}, 1),
        ({"repetitions": 3}, 3),
        ({"k": 2}, 2),
        ({"repetitions": 4, "k": 4}, 4),
    ],
)
def test_evaluator_repetitions_normalizes_new_and_legacy_fields(
    evaluator: dict[str, object], expected: int
) -> None:
    assert config_module.evaluator_repetitions(evaluator) == expected


@pytest.mark.parametrize(
    ("evaluator", "message"),
    [
        ({"repetitions": True}, "evaluator.repetitions must be an integer"),
        ({"repetitions": "2"}, "evaluator.repetitions must be an integer"),
        ({"repetitions": 0}, "evaluator.repetitions must be between 1 and 100"),
        ({"repetitions": 101}, "evaluator.repetitions must be between 1 and 100"),
        ({"k": False}, "evaluator.k must be an integer"),
        ({"repetitions": 2, "k": 3}, "evaluator.repetitions and evaluator.k must be equal"),
    ],
)
def test_evaluator_repetitions_rejects_invalid_values(evaluator: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message.replace(".", r"\.")):
        config_module.evaluator_repetitions(evaluator)


def test_normalize_evaluator_config_writes_repetitions_without_mutating_input() -> None:
    evaluator = {"engine": "harbor", "k": 2}

    normalized = config_module.normalize_evaluator_config(evaluator)

    assert normalized == {"engine": "harbor", "repetitions": 2}
    assert evaluator == {"engine": "harbor", "k": 2}


def test_normalize_evaluator_config_preserves_strict_runtime_profile() -> None:
    evaluator = {
        "engine": "harbor",
        "runtime": {"profile": "harbor-bytedance-v1"},
    }

    normalized = config_module.normalize_evaluator_config(evaluator)

    assert normalized["runtime"] == {"profile": "harbor-bytedance-v1"}


@pytest.mark.parametrize(
    ("runtime", "message"),
    [
        ("harbor-bytedance-v1", "evaluator.runtime must be a mapping"),
        ({}, "evaluator.runtime.profile must be a non-empty string"),
        ({"profile": ""}, "evaluator.runtime.profile must be a non-empty string"),
        (
            {"profile": "harbor-bytedance-v1", "extra": True},
            "unknown evaluator.runtime fields: extra",
        ),
    ],
)
def test_normalize_evaluator_config_rejects_invalid_runtime(
    runtime: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message.replace(".", r"\.")):
        config_module.normalize_evaluator_config({"runtime": runtime})


def test_normalize_evaluator_config_rejects_strict_and_legacy_runtime_together() -> None:
    evaluator = {
        "runtime": {"profile": "harbor-bytedance-uv-v1"},
        "candidate_runtime": {"variant": "uv", "project": "target", "python": "3.12"},
    }

    with pytest.raises(ValueError, match="cannot combine"):
        config_module.normalize_evaluator_config(evaluator)
