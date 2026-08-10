"""HyperAgents fixed validation operator."""

from __future__ import annotations

from pathlib import Path

from evolve.frozen import sdk
from evolve.frozen.interfaces import ValidateOperator, ValidateResult
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, set())
    return config


class HyperAgentsValidate(ValidateOperator):
    def validate(self, checkout: Path, ctx) -> ValidateResult:
        files = [checkout / "operators" / "mutate.py", *sorted((checkout / "target").rglob("*.py"))]
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
        return ValidateResult(True, "mutate and task-agent Python compile", ["validate/compile.log"])


if __name__ == "__main__":
    sdk.main(HyperAgentsValidate, validate_config=validate_config)
