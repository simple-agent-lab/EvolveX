"""Generate the Selected Lineage identity assets used by the public README."""

from __future__ import annotations

import argparse
import html
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PALETTE = {
    "core": "#10372e",
    "lineage": "#19785a",
    "lineage_on_core": "#338e6b",
    "verified": "#65ce9f",
    "explored": "#b5d3c7",
    "explored_on_surface": "#608675",
    "surface": "#f2fbf7",
    "ink": "#18362b",
    "sub": "#607169",
    "white": "#ffffff",
}


def esc(value: str) -> str:
    return html.escape(value)


def render_mark() -> str:
    p = PALETTE
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" '
        'viewBox="0 0 128 128" role="img" aria-labelledby="mark-title mark-description">',
        '  <title id="mark-title">Evolve selected lineage mark</title>',
        '  <desc id="mark-description">A selected candidate path rises past explored side branches to a verified generation.</desc>',
        f'  <rect x="4" y="4" width="120" height="120" rx="28" fill="{p["core"]}"/>',
        f'  <path d="M 48 82 L 68 103 M 66 61 L 45 38 M 86 42 L 105 62" '
        f'fill="none" stroke="{p["explored"]}" stroke-width="4" stroke-linecap="round" '
        'data-state="explored"/>',
        f'  <path d="M 25 101 C 43 93 44 72 62 65 S 86 40 105 23" '
        f'fill="none" stroke="{p["lineage_on_core"]}" stroke-width="7" stroke-linecap="round" '
        'data-state="selected"/>',
    ]
    for cx, cy in ((25, 101), (48, 82), (66, 61), (86, 42)):
        svg.append(
            f'  <circle cx="{cx}" cy="{cy}" r="7" fill="{p["core"]}" '
            f'stroke="{p["verified"]}" stroke-width="4" data-state="selected"/>'
        )
    svg.extend(
        [
            f'  <circle cx="105" cy="23" r="10" fill="{p["verified"]}" '
            f'stroke="{p["white"]}" stroke-width="3"/>',
            f'  <path d="M 100 23 L 104 27 L 111 18" fill="none" stroke="{p["white"]}" '
            'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>',
            '</svg>',
        ]
    )
    return "\n".join(svg) + "\n"


def render_lineage() -> str:
    p = PALETTE
    font = '-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif'
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="360" '
        'viewBox="0 0 960 360" role="img" aria-labelledby="lineage-title lineage-description">',
        '  <title id="lineage-title">Verified candidate lineage</title>',
        '  <desc id="lineage-description">A baseline branches into evaluated candidates. The selected lineage rises through successive generations to a verified improvement while unselected candidates remain visible as evidence.</desc>',
        f'  <rect width="960" height="360" rx="24" fill="{p["surface"]}"/>',
        f'  <path d="M 208 244 L 346 312 M 342 185 L 218 72 M 603 130 L 754 258" '
        f'fill="none" stroke="{p["explored_on_surface"]}" stroke-width="5" '
        'stroke-linecap="round" data-state="explored"/>',
        f'  <path d="M 80 286 C 188 270 188 199 303 197 S 460 142 576 139 S 760 79 866 58" '
        f'fill="none" stroke="{p["lineage"]}" stroke-width="9" stroke-linecap="round" '
        'data-state="selected"/>',
    ]
    for cx, cy in ((80, 286), (208, 244), (342, 185), (603, 130)):
        svg.append(
            f'  <circle cx="{cx}" cy="{cy}" r="13" fill="{p["white"]}" '
            f'stroke="{p["lineage"]}" stroke-width="5" data-state="selected"/>'
        )
    for cx, cy in ((346, 312), (218, 72), (754, 258)):
        svg.append(
            f'  <circle cx="{cx}" cy="{cy}" r="11" fill="{p["surface"]}" '
            f'stroke="{p["explored_on_surface"]}" stroke-width="4" data-state="explored"/>'
        )
    svg.extend(
        [
            f'  <circle cx="866" cy="58" r="20" fill="{p["verified"]}" '
            f'stroke="{p["lineage"]}" stroke-width="6"/>',
            f'  <path d="M 857 58 L 864 65 L 877 48" fill="none" stroke="{p["white"]}" '
            'stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>',
            f'  <g font-family="{font}" font-size="16" fill="{p["sub"]}">',
            '    <text x="48" y="326">baseline</text>',
            '    <text x="150" y="46">explored candidates</text>',
            f'    <text x="470" y="112" fill="{p["lineage"]}" font-weight="700">selected lineage</text>',
            f'    <text x="684" y="38" fill="{p["lineage"]}" font-weight="700">verified generation</text>',
            '  </g>',
            '</svg>',
        ]
    )
    return "\n".join(svg) + "\n"


OUTPUTS: dict[Path, Callable[[], str]] = {
    ROOT / "docs" / "evolve-mark.svg": render_mark,
    ROOT / "docs" / "evolve-lineage.svg": render_lineage,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail when committed assets are stale.")
    args = parser.parse_args()
    stale: list[Path] = []
    for output, renderer in OUTPUTS.items():
        generated = renderer()
        if args.check:
            if not output.exists() or output.read_text() != generated:
                stale.append(output)
        else:
            output.write_text(generated)
            print(f"wrote {output.relative_to(ROOT)}")
    if stale:
        for output in stale:
            print(f"{output.relative_to(ROOT)} is out of date")
        return 1
    if args.check:
        print("README identity assets are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
