#!/usr/bin/env python3
"""Small, dependency-free SVG geometry checker for the paper-poster evaluator."""

from __future__ import annotations

import argparse
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_TRANSFORM = re.compile(r"([A-Za-z]+)\s*\(([^)]*)\)")
Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float
    kind: str
    element: str
    order: int

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _number(value: str | None, default: float = 0.0) -> float:
    if not value:
        return default
    match = re.search(_NUMBER, value)
    return float(match.group(0)) if match else default


def _numbers(value: str | None) -> list[float]:
    return [float(match.group(0)) for match in re.finditer(_NUMBER, value or "")]


def _multiply(left: Matrix, right: Matrix) -> Matrix:
    a1, b1, c1, d1, e1, f1 = left
    a2, b2, c2, d2, e2, f2 = right
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _parse_transform(value: str | None) -> Matrix:
    if not value or not value.strip():
        return IDENTITY
    matrix = IDENTITY
    position = 0
    for match in _TRANSFORM.finditer(value):
        if value[position : match.start()].strip(" ,\t\r\n"):
            raise ValueError(f"unsupported SVG transform syntax: {value}")
        name, arguments = match.group(1), _numbers(match.group(2))
        if name == "matrix" and len(arguments) == 6:
            current: Matrix = tuple(arguments)  # type: ignore[assignment]
        elif name == "translate" and len(arguments) in {1, 2}:
            current = (1.0, 0.0, 0.0, 1.0, arguments[0], arguments[1] if len(arguments) == 2 else 0.0)
        elif name == "scale" and len(arguments) in {1, 2}:
            current = (arguments[0], 0.0, 0.0, arguments[-1], 0.0, 0.0)
        elif name == "rotate" and len(arguments) in {1, 3}:
            angle = math.radians(arguments[0])
            cosine, sine = math.cos(angle), math.sin(angle)
            rotation: Matrix = (cosine, sine, -sine, cosine, 0.0, 0.0)
            if len(arguments) == 1:
                current = rotation
            else:
                center_x, center_y = arguments[1:]
                current = _multiply(
                    _multiply((1.0, 0.0, 0.0, 1.0, center_x, center_y), rotation),
                    (1.0, 0.0, 0.0, 1.0, -center_x, -center_y),
                )
        elif name == "skewX" and len(arguments) == 1:
            current = (1.0, 0.0, math.tan(math.radians(arguments[0])), 1.0, 0.0, 0.0)
        elif name == "skewY" and len(arguments) == 1:
            current = (1.0, math.tan(math.radians(arguments[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            raise ValueError(f"unsupported SVG transform: {name}({match.group(2)})")
        matrix = _multiply(matrix, current)
        position = match.end()
    if position == 0 or value[position:].strip(" ,\t\r\n"):
        raise ValueError(f"unsupported SVG transform syntax: {value}")
    return matrix


def _transform_point(matrix: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def _transform_box(box: Box, matrix: Matrix) -> Box:
    corners = [
        _transform_point(matrix, box.x, box.y),
        _transform_point(matrix, box.right, box.y),
        _transform_point(matrix, box.x, box.bottom),
        _transform_point(matrix, box.right, box.bottom),
    ]
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return Box(
        min(xs),
        min(ys),
        max(xs) - min(xs),
        max(ys) - min(ys),
        box.kind,
        box.element,
        box.order,
    )


def _style_value(element: ET.Element, name: str) -> str | None:
    direct = element.attrib.get(name)
    if direct:
        return direct
    style = element.attrib.get("style", "")
    for declaration in style.split(";"):
        key, separator, value = declaration.partition(":")
        if separator and key.strip() == name:
            return value.strip()
    return None


def _visible(element: ET.Element) -> bool:
    display = _style_value(element, "display")
    visibility = _style_value(element, "visibility")
    opacity = _number(_style_value(element, "opacity"), 1.0)
    return display != "none" and visibility not in {"hidden", "collapse"} and opacity > 0


def _element_id(element: ET.Element, kind: str, order: int) -> str:
    return element.attrib.get("id") or f"{kind}[{order}]"


def _text_box(element: ET.Element, order: int) -> Box | None:
    text = "".join(element.itertext()).strip()
    if not text or not _visible(element):
        return None
    font_size = max(1.0, _number(_style_value(element, "font-size"), 16.0))
    lines = text.splitlines() or [text]
    width = max(
        sum(font_size * (0.33 if char.isspace() else 0.55 if ord(char) < 128 else 1.0) for char in line)
        for line in lines
    )
    height = font_size * 1.2 * len(lines)
    x = _number(_style_value(element, "x"))
    y = _number(_style_value(element, "y"))
    anchor = _style_value(element, "text-anchor")
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    baseline = _style_value(element, "dominant-baseline")
    if baseline in {"middle", "central"}:
        y -= height / 2
    elif baseline in {"hanging", "text-before-edge"}:
        pass
    else:
        y -= font_size * 0.9
    return Box(x, y, width, height, "text", _element_id(element, "text", order), order)


def _shape_box(element: ET.Element, order: int) -> Box | None:
    if not _visible(element):
        return None
    kind = _local_name(element.tag)
    if kind == "rect":
        return Box(
            _number(element.attrib.get("x")),
            _number(element.attrib.get("y")),
            max(0.0, _number(element.attrib.get("width"))),
            max(0.0, _number(element.attrib.get("height"))),
            kind,
            _element_id(element, kind, order),
            order,
        )
    if kind == "circle":
        radius = max(0.0, _number(element.attrib.get("r")))
        return Box(
            _number(element.attrib.get("cx")) - radius,
            _number(element.attrib.get("cy")) - radius,
            radius * 2,
            radius * 2,
            kind,
            _element_id(element, kind, order),
            order,
        )
    if kind == "ellipse":
        radius_x = max(0.0, _number(element.attrib.get("rx")))
        radius_y = max(0.0, _number(element.attrib.get("ry")))
        return Box(
            _number(element.attrib.get("cx")) - radius_x,
            _number(element.attrib.get("cy")) - radius_y,
            radius_x * 2,
            radius_y * 2,
            kind,
            _element_id(element, kind, order),
            order,
        )
    if kind == "line":
        xs = [_number(element.attrib.get("x1")), _number(element.attrib.get("x2"))]
        ys = [_number(element.attrib.get("y1")), _number(element.attrib.get("y2"))]
        return Box(
            min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys), kind, _element_id(element, kind, order), order
        )
    if kind in {"polygon", "polyline"}:
        values = _numbers(element.attrib.get("points"))
        if len(values) < 4:
            return None
        xs, ys = values[::2], values[1::2]
        return Box(
            min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys), kind, _element_id(element, kind, order), order
        )
    return None


def _intersection(left: Box, right: Box) -> float:
    width = max(0.0, min(left.right, right.right) - max(left.x, right.x))
    height = max(0.0, min(left.bottom, right.bottom) - max(left.y, right.y))
    return width * height


def _full_bleed(box: Box, view_box: tuple[float, float, float, float]) -> bool:
    x, y, width, height = view_box
    return box.kind != "text" and box.x <= x and box.y <= y and box.right >= x + width and box.bottom >= y + height


def check_svg(path: Path) -> dict[str, object]:
    root = ET.parse(path).getroot()
    if _local_name(root.tag) != "svg":
        raise ValueError("root element is not svg")
    view_values = _numbers(root.attrib.get("viewBox"))
    if len(view_values) != 4 or view_values[2] <= 0 or view_values[3] <= 0:
        raise ValueError("SVG has no positive four-value viewBox")
    view_box = tuple(view_values)  # type: ignore[assignment]
    x, y, width, height = view_box
    boxes: list[Box] = []
    order = 0

    def collect_boxes(element: ET.Element, parent_matrix: Matrix) -> None:
        nonlocal order
        element_order = order
        order += 1
        matrix = _multiply(parent_matrix, _parse_transform(element.attrib.get("transform")))
        kind = _local_name(element.tag)
        box = _text_box(element, element_order) if kind == "text" else _shape_box(element, element_order)
        if box is not None and box.area > 0:
            boxes.append(_transform_box(box, matrix))
        for child in element:
            collect_boxes(child, matrix)

    collect_boxes(root, IDENTITY)

    issues: list[dict[str, object]] = []
    text_overflow = 0
    node_overflow = 0
    for box in boxes:
        if _full_bleed(box, view_box):
            continue
        overflow = {
            "left": max(0.0, x - box.x),
            "top": max(0.0, y - box.y),
            "right": max(0.0, box.right - (x + width)),
            "bottom": max(0.0, box.bottom - (y + height)),
        }
        if any(value > 0.01 for value in overflow.values()):
            if box.kind == "text":
                text_overflow += 1
            else:
                node_overflow += 1
            issues.append(
                {
                    "kind": "textOverflow" if box.kind == "text" else "nodeOverflow",
                    "severity": "error",
                    "element": box.element,
                    "message": f"{box.kind} extends outside the viewBox",
                    "overflow": {key: round(value, 2) for key, value in overflow.items() if value > 0.01},
                }
            )

    text_boxes = [box for box in boxes if box.kind == "text"]
    node_overlap = 0
    for index, left in enumerate(text_boxes):
        for right in text_boxes[index + 1 :]:
            if _intersection(left, right) > 1.0:
                node_overlap += 1
                issues.append(
                    {
                        "kind": "nodeOverlap",
                        "severity": "warning",
                        "elements": [left.element, right.element],
                        "message": "text bounding boxes overlap",
                    }
                )

    text_occlusion = 0
    for text in text_boxes:
        for shape in boxes:
            if shape.kind == "text" or shape.order <= text.order:
                continue
            intersection = _intersection(text, shape)
            if intersection / text.area >= 0.8:
                text_occlusion += 1
                issues.append(
                    {
                        "kind": "textOcclusion",
                        "severity": "warning",
                        "elements": [text.element, shape.element],
                        "message": "a later shape covers most of a text bounding box",
                    }
                )

    return {
        "checker": "local-svg-geometry-v1",
        "valid": not any(issue["severity"] == "error" for issue in issues),
        "summary": {
            "textOverflow": text_overflow,
            "nodeOverflow": node_overflow,
            "nodeOverlap": node_overlap,
            "textOcclusion": text_occlusion,
        },
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--format", choices=["json"], default="json")
    args = parser.parse_args()
    try:
        print(json.dumps(check_svg(args.input), sort_keys=True))
    except (OSError, ET.ParseError, ValueError) as exc:
        print(json.dumps({"checker": "local-svg-geometry-v1", "valid": False, "error": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
