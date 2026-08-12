#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "task_assets"


def extract_pdf_text(source: Path, destination: Path) -> None:
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        subprocess.run(
            [pdftotext, "-layout", str(source), str(destination)],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return
    if platform.system() == "Darwin" and shutil.which("swift"):
        script = """\
import Foundation
import PDFKit

guard CommandLine.arguments.count == 2,
      let document = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1])) else {
    exit(2)
}
for index in 0..<document.pageCount {
    if let text = document.page(at: index)?.string {
        print(text)
    }
}
"""
        completed = subprocess.run(
            ["swift", "-", str(source)],
            input=script,
            text=True,
            check=True,
            capture_output=True,
            timeout=120,
        )
        destination.write_text(completed.stdout)
        return
    raise RuntimeError(
        "paper text extraction requires pdftotext, or Swift PDFKit on macOS; "
        "prepare the frozen dataset on a supported host"
    )


def load_cases() -> list[dict[str, object]]:
    return [json.loads(line) for line in (ROOT / "paper_cases.jsonl").read_text().splitlines() if line.strip()]


def download(url: str, destination: Path) -> str:
    if not destination.is_file():
        pending = destination.with_suffix(".pending")
        request = urllib.request.Request(url, headers={"User-Agent": "rsihub-paper-poster/1"})
        with urllib.request.urlopen(request, timeout=120) as response, pending.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        pending.replace(destination)
    data = destination.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise RuntimeError(f"downloaded source is not a PDF: {url}")
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def write_task(case: dict[str, object], output: Path, cache: Path) -> dict[str, object]:
    task_id = str(case["id"])
    task = output / task_id
    environment = task / "environment"
    tests = task / "tests"
    environment.mkdir(parents=True, exist_ok=True)
    tests.mkdir(parents=True, exist_ok=True)

    cached_pdf = cache / f"{task_id}.pdf"
    digest = download(str(case["pdf_url"]), cached_pdf)
    shutil.copy2(cached_pdf, environment / "paper.pdf")
    extract_pdf_text(cached_pdf, environment / "paper.txt")
    shutil.copy2(ASSETS / "Dockerfile", environment / "Dockerfile")
    shutil.copy2(ASSETS / "evaluate.py", tests / "evaluate.py")
    shutil.copy2(ASSETS / "svg_check.py", tests / "svg_check.py")
    shutil.copy2(ASSETS / "judge_schema.json", tests / "judge_schema.json")
    shutil.copy2(ROOT / "rubric.json", tests / "rubric.json")
    shutil.copy2(ASSETS / "test.sh", tests / "test.sh")
    (tests / "test.sh").chmod(0o755)
    (tests / "evaluate.py").chmod(0o755)
    (task / "instruction.md").write_text(str(case["prompt"]) + "\n")
    (task / "task.toml").write_text(
        'version = "1.0"\n\n'
        "[metadata]\n"
        f"name = {json.dumps(task_id)}\n"
        f"paper_title = {json.dumps(str(case['title']))}\n"
        f"paper_source = {json.dumps(str(case['source_version']))}\n\n"
        "[verifier]\n"
        "timeout_sec = 1200.0\n\n"
        "[agent]\n"
        "timeout_sec = 1800.0\n\n"
        "[environment]\n"
        "build_timeout_sec = 1200.0\n"
    )
    return {"id": task_id, "pdf_sha256": digest, "source_version": case["source_version"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("runs/datasets/paper-poster-v1"))
    parser.add_argument("--cache", type=Path, default=Path("runs/datasets/paper-poster-pdf-cache"))
    args = parser.parse_args()
    output = args.output.resolve()
    cache = args.cache.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    manifest = [write_task(case, output, cache) for case in load_cases()]
    (output / "dataset-source.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "tasks": len(manifest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
