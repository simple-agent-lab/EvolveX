from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    target = Path("target/agent.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    marker = f"# smoke-mutate gen {os.environ['EVOLVE_GENID']}"

    if marker not in existing.splitlines():
        prefix = existing.rstrip("\n")
        target.write_text(f"{prefix}\n{marker}\n" if prefix else f"{marker}\n", encoding="utf-8")

    print("predicted_fixes: []")


if __name__ == "__main__":
    main()
