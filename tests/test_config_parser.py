from pathlib import Path

import pytest

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
        "    variant: ahe_trace_analysis\n"
        "    controls:\n"
        "      successful: 3\n"
        "      labels: [stable, 'contains: colon']\n"
        "    analyze:\n"
        "      failures: true\n"
        "      thresholds: {partial: 0.5, retry: null}\n"
        "evaluator: {}\n"
    )

    assert operator_blocks(workspace)["rollout"] == {
        "variant": "ahe_trace_analysis",
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


def test_unknown_top_level_section_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "evolve.yaml").write_text("experiment: {}\nahe: {}\n")

    with pytest.raises(ValueError, match="unknown top-level config sections: ahe"):
        operator_blocks(workspace)
