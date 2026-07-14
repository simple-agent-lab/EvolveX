"""HyperAgents fixed validation operator."""

# ruff: noqa: E402

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import ValidateOperator, ValidateResult


class HyperAgentsValidate(ValidateOperator):
    def validate(self, checkout: Path, ctx) -> ValidateResult:
        files = [checkout / "operators" / "meta_agent.py", *sorted((checkout / "target").rglob("*.py"))]
        log = ctx.run_dir / "validate" / "compile.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        checked = []
        try:
            for path in files:
                compile(path.read_bytes(), str(path), "exec")
                checked.append(path.relative_to(checkout).as_posix())
        except (OSError, SyntaxError) as exc:
            relative = path.relative_to(checkout).as_posix()
            log.write_text(f"FAIL {relative}: {exc}\n")
            return ValidateResult(False, f"compile failed for {relative}", ["validate/compile.log"])
        log.write_text("\n".join(f"PASS {path}" for path in checked) + "\n")
        return ValidateResult(True, "meta-agent and task-agent Python compile", ["validate/compile.log"])


if __name__ == "__main__":
    sdk.main(HyperAgentsValidate)
