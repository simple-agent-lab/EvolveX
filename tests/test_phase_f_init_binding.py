from pathlib import Path

from conftest import run_evolve

from evolve import __version__

ROOT = Path(__file__).resolve().parents[1]


def _provenance_and_body(bound_source: str) -> tuple[str, str]:
    header, body = bound_source.split("\n\n", 1)
    assert header.startswith("# evolve-provenance:")
    return header, body


def test_init_binds_dgm_select_to_score_weighted_library_variant_and_stamps_protocol(tmp_path: Path) -> None:
    workspace = tmp_path / "dgm-workspace"

    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "dgm",
        env={"EVOLVE_HOME": str(tmp_path / "home")},
    )

    assert result.returncode == 0, result.stderr
    expected_source = (ROOT / "library" / "select" / "score_weighted.py").read_text()
    header, body = _provenance_and_body((workspace / "operators" / "select.py").read_text())
    assert "kind=select" in header
    assert "source=library/select/score_weighted.py" in header
    assert f"framework_version={__version__}" in header
    assert "this file is yours now" in header
    assert "mechanism will never overwrite it" in header
    assert "evolve it" in header
    assert body == expected_source
    assert (workspace / ".evolve-protocol-version").read_text() == "1\n"
