from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python_sources() -> list[Path]:
    roots = (ROOT / "library", ROOT / "src", ROOT / "templates")
    return sorted(path for root in roots for path in root.rglob("*.py"))


def test_production_python_does_not_mutate_sys_path() -> None:
    violations: list[str] = []
    for path in _python_sources():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "sys" and node.attr == "path":
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert violations == []


def test_shell_entry_points_do_not_set_pythonpath() -> None:
    violations = []
    for path in sorted((ROOT / "templates").rglob("*.sh")):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if "PYTHONPATH=" in line:
                violations.append(f"{path.relative_to(ROOT)}:{lineno}")

    assert violations == []


def test_ci_verifies_linux_and_macos() -> None:
    workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text()

    assert "os: [ubuntu-latest, macos-latest]" in workflow
    assert "runs-on: ${{ matrix.os }}" in workflow
