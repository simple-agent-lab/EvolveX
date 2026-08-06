from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "evals" / "skills" / "make-paper-poster" / "task_assets" / "svg_check.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("paper_poster_svg_checker", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_svg_checker_reports_overflow_and_overlap(tmp_path: Path) -> None:
    module = _load_checker()
    path = tmp_path / "poster.svg"
    path.write_text(
        '<svg viewBox="0 0 100 100">'
        '<rect id="background" x="0" y="0" width="100" height="100"/>'
        '<text id="overflow" x="98" y="20" font-size="10">overflow</text>'
        '<text id="first" x="10" y="40" font-size="10">same place</text>'
        '<text id="second" x="10" y="40" font-size="10">same place</text>'
        '<rect id="occluder" x="9" y="29" width="80" height="15"/>'
        "</svg>"
    )

    result = module.check_svg(path)

    assert result["checker"] == "local-svg-geometry-v1"
    assert result["valid"] is False
    summary = result["summary"]
    assert summary["textOverflow"] == 1
    assert summary["nodeOverlap"] >= 1
    assert summary["textOcclusion"] >= 1
    assert {issue["kind"] for issue in result["issues"]} >= {
        "textOverflow",
        "nodeOverlap",
        "textOcclusion",
    }


def test_local_svg_checker_ignores_full_bleed_background(tmp_path: Path) -> None:
    module = _load_checker()
    path = tmp_path / "poster.svg"
    path.write_text(
        '<svg viewBox="0 0 100 100">'
        '<rect x="0" y="0" width="100" height="100"/>'
        '<text x="10" y="20" font-size="10">inside</text>'
        "</svg>"
    )

    result = module.check_svg(path)

    assert result["valid"] is True
    assert result["summary"] == {"textOverflow": 0, "nodeOverlap": 0, "textOcclusion": 0}
