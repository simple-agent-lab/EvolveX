#!/usr/bin/env python3
"""Model-free smoke for the pinned local paper-poster renderer."""

from __future__ import annotations

import json
import os
import struct
import subprocess
from pathlib import Path


def main() -> int:
    root = Path(os.environ["EVOLVE_DOCTOR_TEMP"])
    renderer = os.environ["EVOLVE_SVG_RENDERER"]
    expected_digest = os.environ["EVOLVE_SVG_RUNTIME_DIGEST"]
    source = root / "doctor.svg"
    output = root / "doctor.png"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 36">'
        '<rect width="64" height="36" fill="#fff"/>'
        '<text x="4" y="22" font-family="Noto Sans" font-size="12">Evolve</text>'
        "</svg>"
    )
    result = subprocess.run(
        [renderer, str(source), "--width", "64", "--output", str(output)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    payload = json.loads(result.stdout)
    header = output.read_bytes()[:24]
    dimensions = struct.unpack(">II", header[16:24]) if header[:8] == b"\x89PNG\r\n\x1a\n" else None
    if payload.get("runtime_digest") != expected_digest or dimensions != (64, 36):
        raise RuntimeError("local SVG renderer returned an inconsistent smoke receipt")
    print(json.dumps({"runtime_digest": expected_digest, "dimensions": dimensions}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
