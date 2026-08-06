#!/usr/bin/env python3
"""Render one static SVG with the frozen paper-poster resvg toolchain."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import tempfile
from pathlib import Path


def svg_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise RuntimeError(f"renderer did not produce a valid PNG: {path}")
    return struct.unpack(">II", header[16:24])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int)
    args = parser.parse_args()

    source = args.input.resolve()
    if not source.is_file():
        raise SystemExit(f"SVG input does not exist: {source}")
    if args.width < 1 or (args.height is not None and args.height < 1):
        raise SystemExit("render dimensions must be positive")

    digest = svg_digest(source)
    output = args.output.resolve() if args.output is not None else source.with_name(f"{source.stem}-{digest[:12]}.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    runtime_root = Path(__file__).resolve().parent.parent
    renderer = runtime_root / "bin" / "resvg"
    fonts = runtime_root / "fonts"
    receipt_path = runtime_root / "runtime.json"
    if not renderer.is_file() or not fonts.is_dir() or not receipt_path.is_file():
        raise SystemExit(f"incomplete paper-poster renderer runtime: {runtime_root}")

    if args.output is None and output.is_file():
        width, height = png_dimensions(output)
        print(
            json.dumps(
                {
                    "cached": True,
                    "input_sha256": digest,
                    "output": str(output),
                    "runtime_digest": json.loads(receipt_path.read_text())["runtime_digest"],
                    "width": width,
                    "height": height,
                },
                sort_keys=True,
            )
        )
        return 0

    command = [
        str(renderer),
        "--quiet",
        "--width",
        str(args.width),
        "--background",
        "#ffffff",
        "--resources-dir",
        str(source.parent),
        "--skip-system-fonts",
        "--use-fonts-dir",
        str(fonts),
        "--font-family",
        "Noto Sans",
        "--sans-serif-family",
        "Noto Sans",
        "--serif-family",
        "Noto Sans",
    ]
    if args.height is not None:
        command.extend(["--height", str(args.height)])

    temporary_fd, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(temporary_fd)
    temporary = Path(temporary_name)
    try:
        command.extend([str(source), str(temporary)])
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
        width, height = png_dimensions(temporary)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)

    receipt = json.loads(receipt_path.read_text())
    print(
        json.dumps(
            {
                "cached": False,
                "engine": "resvg",
                "engine_version": receipt["renderer"]["version"],
                "input_sha256": digest,
                "output": str(output),
                "runtime_digest": receipt["runtime_digest"],
                "width": width,
                "height": height,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
