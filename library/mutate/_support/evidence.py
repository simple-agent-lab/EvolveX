"""Load the normalized feedback bundle assembled before meta-agent execution."""

from __future__ import annotations

import re
from pathlib import Path


def load_feedback(run_dir: Path, fallback: str = "") -> str:
    root = (run_dir / "feedback").resolve()
    index = root / "index.md"
    seen: set[Path] = set()
    parts: list[tuple[str, str]] = []
    if index.is_file():
        text = index.read_text()
        parts.append(("feedback/index.md", text))
        seen.add(index.resolve())
        for relative in re.findall(r"\[[^\]]+\]\(([^)#]+)", text):
            path = (root / relative.strip()).resolve()
            if path.is_file() and root in path.parents and path not in seen:
                parts.append((f"feedback/{path.relative_to(root).as_posix()}", path.read_text()))
                seen.add(path)
    rules = root / "rules.md"
    if rules.is_file() and rules.resolve() not in seen:
        parts.append(("feedback/rules.md", rules.read_text()))
    rendered = "\n".join("## %s\n%s" % (name, text.rstrip()) for name, text in parts if text.strip())
    return rendered or fallback.strip()
