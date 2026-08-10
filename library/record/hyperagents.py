"""HyperAgents compact experience record operator."""

from __future__ import annotations

import json

from evolve.frozen import sdk
from evolve.frozen.interfaces import RecordOperator, RecordResult
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, set())
    return config


class HyperAgentsRecord(RecordOperator):
    def annotate(self, child, ctx) -> RecordResult:
        experience = {key: child.get(key) for key in ("genid", "parent", "status", "score")}
        path = ctx.run_dir / "record" / "experience.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(experience, indent=2, sort_keys=True) + "\n")
        relative = path.relative_to(ctx.workspace).as_posix()
        return RecordResult(fields={"experience_record": relative})


if __name__ == "__main__":
    sdk.main(HyperAgentsRecord, validate_config=validate_config)
