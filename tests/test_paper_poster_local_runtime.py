from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

from evolve import workspace as workspace_module

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "evals" / "skills" / "make-paper-poster" / "recipe" / "evaluator"
POSTER_EVAL = ROOT / "evals" / "skills" / "make-paper-poster"


def _load_prepare_module():
    path = RUNTIME / "prepare_poster_runtime.py"
    spec = importlib.util.spec_from_file_location("paper_poster_runtime", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _minimal_png(width: int = 1600, height: int = 900) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height)


def test_runtime_manifest_pins_supported_assets_and_fonts() -> None:
    module = _load_prepare_module()

    assert module.renderer_asset("darwin", "arm64").sha256 == (
        "06440eb5aa14a28cbfc7e40ae39e1ffa71adc051b89fbaa913b4f1d9b905d09f"
    )
    assert module.renderer_asset("linux", "x86_64").name == "resvg-linux-x86_64.tar.gz"
    assert {font.name for font in module.FONT_ASSETS} == {"NotoSans.ttf", "NotoSans-Italic.ttf"}


def test_poster_recipe_vendors_frozen_local_runtime_assets() -> None:
    recipe = RUNTIME.parent
    assets = workspace_module._recipe_evaluator_assets("unused", recipe_directory=recipe)

    assert set(assets) == {
        "evaluator/doctor.json",
        "evaluator/doctor_smoke.py",
        "evaluator/prepare-runtime.sh",
        "evaluator/prepare_poster_runtime.py",
        "evaluator/render_svg.py",
    }


def test_poster_doctor_contract_pins_current_task_assets() -> None:
    contract = json.loads((RUNTIME / "doctor.json").read_text())

    expected = contract["tasks"]["sha256"]
    sources = {
        "tests/evaluate.py": POSTER_EVAL / "task_assets" / "evaluate.py",
        "tests/svg_check.py": POSTER_EVAL / "task_assets" / "svg_check.py",
        "tests/judge_schema.json": POSTER_EVAL / "task_assets" / "judge_schema.json",
        "tests/test.sh": POSTER_EVAL / "task_assets" / "test.sh",
        "tests/rubric.json": POSTER_EVAL / "rubric.json",
    }
    assert expected == {
        name: f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}" for name, path in sources.items()
    }


def test_poster_runtime_hook_is_a_noop_for_existing_docker_evaluators(tmp_path: Path) -> None:
    env_out = tmp_path / "runtime.env"
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    subprocess.run(
        ["sh", str(RUNTIME / "prepare-runtime.sh"), str(run_dir), str(env_out)],
        check=True,
        env={**os.environ, "EVOLVE_HARBOR_ENVIRONMENT": "docker"},
    )

    assert env_out.read_text() == ""


def test_poster_dataset_freezes_paper_text_and_keeps_legacy_fallback() -> None:
    prepare = (POSTER_EVAL / "prepare_dataset.py").read_text()
    evaluator = (POSTER_EVAL / "task_assets" / "evaluate.py").read_text()
    dockerfile = (POSTER_EVAL / "task_assets" / "Dockerfile").read_text()

    assert 'extract_pdf_text(cached_pdf, environment / "paper.txt")' in prepare
    assert "if not PAPER_TEXT.is_file():" in evaluator
    assert "COPY paper.txt /root/task/paper.txt" in dockerfile


def test_render_wrapper_uses_frozen_fonts_atomic_output_and_content_addressing(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    bin_dir = runtime / "bin"
    fonts = runtime / "fonts"
    bin_dir.mkdir(parents=True)
    fonts.mkdir()
    wrapper = bin_dir / "evolve-render-svg"
    wrapper.write_text((RUNTIME / "render_svg.py").read_text())
    fake_renderer = bin_dir / "resvg"
    fake_renderer.write_text(
        "#!/usr/bin/env python3\n"
        "import json,os,struct,sys\n"
        "open(os.environ['FAKE_RESVG_LOG'], 'w').write(json.dumps(sys.argv[1:]))\n"
        "open(sys.argv[-1], 'wb').write(b'\\x89PNG\\r\\n\\x1a\\n' + b'\\x00\\x00\\x00\\rIHDR' + struct.pack('>II', 1600, 900))\n"
    )
    fake_renderer.chmod(0o755)
    (fonts / "NotoSans.ttf").write_bytes(b"font")
    (runtime / "runtime.json").write_text(
        json.dumps({"renderer": {"version": "test"}, "runtime_digest": "sha256:test"})
    )
    svg = tmp_path / "poster.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9"/>')
    log = tmp_path / "resvg-args.json"
    environment = {**os.environ, "FAKE_RESVG_LOG": str(log)}

    result = subprocess.run(
        [sys.executable, str(wrapper), str(svg), "--width", "1600"],
        text=True,
        capture_output=True,
        env=environment,
        check=True,
    )

    receipt = json.loads(result.stdout)
    output = Path(receipt["output"])
    arguments = json.loads(log.read_text())
    assert output.name.startswith("poster-") and output.suffix == ".png"
    assert output.read_bytes() == _minimal_png()
    assert "--skip-system-fonts" in arguments
    assert arguments[arguments.index("--use-fonts-dir") + 1] == str(fonts)
    assert receipt["runtime_digest"] == "sha256:test"

    cached = subprocess.run(
        [sys.executable, str(wrapper), str(svg), "--width", "1600"],
        text=True,
        capture_output=True,
        env=environment,
        check=True,
    )
    assert json.loads(cached.stdout)["cached"] is True
