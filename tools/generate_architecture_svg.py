"""Generate the README architecture diagram.

Three bands, one story: evolution methods plug into one loop, the loop and the
agent it improves sit inside a declared mutable surface, and only the substrate
underneath stays frozen.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "architecture.svg"

PALETTE = {
    "ink": "#18362b",
    "sub": "#607169",
    "line": "#b5d3c7",
    "soft": "#dce9e3",
    "band_fill": "#f7fbf9",
    "band_line": "#dce9e3",
    "chip_fill": "#eff7f3",
    "chip_line": "#b5d3c7",
    "open_line": "#9fc5b5",
    "stage_line": "#b5d3c7",
    "accent_fill": "#dcf5e9",
    "accent_line": "#65ce9f",
    "accent_text": "#19785a",
    "guard_fill": "#10372e",
    "guard_line": "#10372e",
    "guard_text": "#ffffff",
    "surface_fill": "#f2fbf7",
}

FONT = '"Noto Sans SC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'

W, H = 1240, 520
M = 44
INNER = W - 2 * M

METHODS = ["Hill Climb", "A-Evolve", "AHE", "GEPA", "HyperAgents"]

STAGES = [
    ("Select", "choose a parent"),
    ("Rollout", "run tasks + evaluator"),
    ("Analyze", "inspect the traces"),
    ("Mutate", "edit the candidate"),
    ("Gate", "accept verified gains"),
    ("Record", "tag + archive"),
]

GUARDS = [
    ("Frozen evaluator", "pinned scoring contract"),
    ("Locked runtime", "pinned deps + digest"),
    ("Surface check", "declared paths only"),
    ("Stamped evidence", "archive + git lineage"),
]


def esc(value: str) -> str:
    return html.escape(value)


def text(value: str, x: float, y: float, cls: str, anchor: str = "start") -> str:
    anchor_attr = "" if anchor == "start" else f' text-anchor="{anchor}"'
    return f'  <text x="{x:g}" y="{y:g}"{anchor_attr} class="{cls}">{esc(value)}</text>'


def rect(x: float, y: float, w: float, h: float, r: float, cls: str) -> str:
    return f'  <rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{r:g}" class="{cls}"/>'


def line(x1: float, y1: float, x2: float, y2: float, cls: str = "flow") -> str:
    return f'  <line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" class="{cls}"/>'


def circle(cx: float, cy: float, r: float, cls: str) -> str:
    return f'  <circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" class="{cls}"/>'


def arrow(x: float, y: float, direction: str, cls: str = "arrow-fill", scale: float = 1.0) -> str:
    size, wing = 9 * scale, 5 * scale
    if direction == "down":
        points = f"{x},{y} {x - wing},{y - size} {x + wing},{y - size}"
    elif direction == "up":
        points = f"{x},{y} {x - wing},{y + size} {x + wing},{y + size}"
    elif direction == "right":
        points = f"{x},{y} {x - size},{y - wing} {x - size},{y + wing}"
    else:  # pragma: no cover - programming error
        raise ValueError(direction)
    return f'  <polygon points="{points}" class="{cls}"/>'


def route(points: list[tuple[float, float]], radius: float = 12, cls: str = "flow") -> str:
    """An orthogonal connector with rounded corners."""

    def shift(a: tuple[float, float], b: tuple[float, float], r: float) -> tuple[float, float]:
        dx, dy = b[0] - a[0], b[1] - a[1]
        step = min(r, max(abs(dx), abs(dy)) / 2)
        return a[0] + (step if dx > 0 else -step if dx < 0 else 0), a[1] + (step if dy > 0 else -step if dy < 0 else 0)

    d = [f"M {points[0][0]:g} {points[0][1]:g}"]
    for i in range(1, len(points) - 1):
        before, corner, after = points[i - 1], points[i], points[i + 1]
        entry, exit_ = shift(corner, before, radius), shift(corner, after, radius)
        d.append(f"L {entry[0]:g} {entry[1]:g}")
        d.append(f"Q {corner[0]:g} {corner[1]:g} {exit_[0]:g} {exit_[1]:g}")
    d.append(f"L {points[-1][0]:g} {points[-1][1]:g}")
    return f'  <path d="{" ".join(d)}" class="{cls}"/>'


def node(
    x: float,
    y: float,
    w: float,
    h: float,
    cls: str,
    title: str,
    sub: str | None = None,
    r: float = 12,
    title_cls: str = "t",
    sub_cls: str = "s",
) -> list[str]:
    cx = x + w / 2
    if sub:
        return [
            rect(x, y, w, h, r, cls),
            text(title, cx, y + h / 2 - 3, title_cls, "middle"),
            text(sub, cx, y + h / 2 + 19, sub_cls, "middle"),
        ]
    return [rect(x, y, w, h, r, cls), text(title, cx, y + h / 2 + 6, title_cls, "middle")]


def row(x: float, width: float, count: int, gap: float) -> tuple[list[float], float]:
    """Left edges and item width for `count` evenly spaced boxes."""
    item = (width - gap * (count - 1)) / count
    return [x + i * (item + gap) for i in range(count)], item


def style() -> str:
    p = PALETTE
    return f"""  <style>
    text {{ font-family: {FONT}; fill: {p["ink"]}; }}
    .t {{ font-size: 16px; font-weight: 600; }}
    .s {{ font-size: 13px; fill: {p['sub']}; }}
    .t-guard {{ font-size: 16px; font-weight: 600; fill: {p['guard_text']}; }}
    .s-guard {{ font-size: 13px; fill: {p['guard_text']}; }}
    .cap {{ font-size: 13px; fill: {p['sub']}; }}
    .cap-accent {{ font-size: 13px; fill: {p['accent_text']}; }}
    .lbl {{ font-size: 13px; font-weight: 600; letter-spacing: 0.08em; fill: {p['sub']}; }}
    .lbl-accent {{ font-size: 13px; font-weight: 600; letter-spacing: 0.08em; fill: {p['accent_text']}; }}
    .canvas {{ fill: #ffffff; }}
    .knock {{ fill: {p['band_fill']}; }}
    .band {{ fill: {p['band_fill']}; stroke: {p['band_line']}; stroke-width: 1.5; }}
    .chip {{ fill: {p['chip_fill']}; stroke: {p['chip_line']}; stroke-width: 1.5; }}
    .open {{ fill: #ffffff; stroke: {p['open_line']}; stroke-width: 1.5; stroke-dasharray: 6 5; }}
    .stage {{ fill: #ffffff; stroke: {p['stage_line']}; stroke-width: 1.5; }}
    .accent {{ fill: {p['accent_fill']}; stroke: {p['accent_line']}; stroke-width: 1.5; }}
    .guard {{ fill: {p['guard_fill']}; stroke: {p['guard_line']}; stroke-width: 1.5; }}
    .mutable {{ fill: {p['surface_fill']}; stroke: {p['accent_line']}; stroke-width: 1.5; stroke-dasharray: 7 6; }}
    .flow {{ fill: none; stroke: {p['line']}; stroke-width: 1.8; }}
    .soft {{ fill: none; stroke: {p['soft']}; stroke-width: 1.4; }}
    .flow-accent {{ fill: none; stroke: {p['accent_line']}; stroke-width: 1.4; }}
    .tick-accent {{ fill: none; stroke: {p['accent_line']}; stroke-width: 1.4; stroke-dasharray: 5 4; }}
    .arrow-fill {{ fill: {p['line']}; }}
    .arrow-accent {{ fill: {p['accent_line']}; }}
    .dot-accent {{ fill: {p['accent_line']}; stroke: none; }}
  </style>"""


def methods_band() -> list[str]:
    """The top band: five known methods plus room for one of yours."""
    body = [
        text("EVOLUTION METHODS", M, 26, "lbl"),
        text("Five built-in strategies, or compose your own", W - M, 26, "cap", "end"),
    ]
    xs, cw = row(M, INNER, 6, 14)
    for x, label in zip(xs, METHODS, strict=False):
        body.extend(node(x, 38, cw, 54, "chip", label))
    body.extend(node(xs[5], 38, cw, 54, "open", "your recipe"))

    first, last = xs[0] + cw / 2, xs[5] + cw / 2
    body.append(route([(first, 92), (first, 106), (last, 106), (last, 92)], 12, "soft"))
    for x in xs[1:5]:
        body.append(line(x + cw / 2, 92, x + cw / 2, 106, "soft"))
    body.append(line(W / 2, 106, W / 2, 119))
    body.append(arrow(W / 2, 128, "down"))
    return body


def loop_band() -> list[str]:
    """The middle band: one loop, and the surface that makes it editable."""
    body = [
        rect(M, 140, INNER, 226, 16, "band"),
        text("ONE COMPOSABLE LOOP", M + 22, 164, "lbl"),
        text("recipes choose which stages and targets may evolve", W - M - 22, 164, "cap-accent", "end"),
        rect(M + 16, 178, INNER - 32, 134, 14, "mutable"),
        rect(W / 2 - 172, 167, 344, 22, 11, "knock"),
        text("DECLARED MUTABLE SURFACE · target + selected operators", W / 2, 183, "lbl-accent", "middle"),
    ]

    xs, sw = row(M + 32, INNER - 64, 6, 18)
    centers = [x + sw / 2 for x in xs]
    edit = centers[3]
    body.append(line(centers[0], 204, centers[5], 204, "flow-accent"))
    body.append(line(edit, 204, edit, 228, "flow-accent"))
    body.append(circle(edit, 204, 3.5, "dot-accent"))
    for i, cx in enumerate(centers):
        if i == 3:
            continue
        body.append(line(cx, 204, cx, 221, "tick-accent"))
        body.append(arrow(cx, 228, "down", "arrow-accent", 0.8))

    for x, (title, sub) in zip(xs, STAGES, strict=True):
        cls = "accent" if title in {"Mutate", "Gate"} else "stage"
        body.extend(node(x, 228, sw, 64, cls, title, sub))
    for x in xs[:-1]:
        body.append(line(x + sw + 2, 260, x + sw + 7, 260))
        body.append(arrow(x + sw + 16, 260, "right"))

    body.append(route([(centers[5], 292), (centers[5], 332), (centers[0], 332), (centers[0], 303)]))
    body.append(arrow(centers[0], 294, "up"))
    body.append(text("next generation", W / 2, 352, "cap", "middle"))
    return body


def substrate_band() -> list[str]:
    """The bottom band: the only part nothing in the loop can touch."""
    body = [
        line(400, 366, 400, 388),
        arrow(400, 397, "down"),
        text("evidence", 412, 393, "cap"),
        line(840, 397, 840, 375),
        arrow(840, 366, "up"),
        text("contracts", 852, 393, "cap"),
        text("PROTECTED MECHANISM", M, 420, "lbl"),
        text("outside candidate control", W - M, 420, "cap", "end"),
    ]
    xs, gw = row(M, INNER, 4, 16)
    for x, (title, sub) in zip(xs, GUARDS, strict=True):
        body.extend(
            node(
                x,
                434,
                gw,
                58,
                "guard",
                title,
                sub,
                title_cls="t-guard",
                sub_cls="s-guard",
            )
        )
    return body


def render() -> str:
    description = (
        "Evolution methods such as Hill Climb, A-Evolve, AHE, GEPA and HyperAgents plug into one loop of "
        "select, rollout, analyze, mutate, gate and record. The loop and the agent it improves sit inside a "
        "declared mutable surface. Recipes select permitted targets, operators, and stages. Only the substrate below stays "
        "frozen: the evaluator, the runtime, the surface check and the stamped evidence."
    )
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" aria-labelledby="title description">',
        "  <!-- Generated by tools/generate_architecture_svg.py. -->",
        '  <title id="title">Evolve Framework architecture</title>',
        f'  <desc id="description">{esc(description)}</desc>',
        style(),
        rect(0, 0, W, H, 0, "canvas"),
        "",
        *methods_band(),
        "",
        *loop_band(),
        "",
        *substrate_band(),
        "</svg>",
    ]
    return "\n".join(svg) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the README architecture diagram.")
    parser.add_argument("--check", action="store_true", help="Fail if docs/architecture.svg is not up to date.")
    args = parser.parse_args()
    generated = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != generated:
            print(f"{OUTPUT.relative_to(ROOT)} is out of date; regenerate it with {Path(__file__).relative_to(ROOT)}")
            return 1
        print(f"{OUTPUT.relative_to(ROOT)} is up to date")
        return 0
    OUTPUT.write_text(generated)
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
