from pathlib import Path

from evolve.config import operator_blocks


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
