"""HyperAgents compact experience record operator."""

from __future__ import annotations

import json

from evolve.frozen import sdk
from evolve.frozen.config import Config
from evolve.frozen.interfaces import RecordOperator, RecordResult

CONFIG = Config({})


class HyperAgentsRecord(RecordOperator):
    def annotate(self, child, ctx) -> RecordResult:
        experience = {key: child.get(key) for key in ("genid", "parent", "status", "score")}
        path = ctx.run_dir / "record" / "experience.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(experience, indent=2, sort_keys=True) + "\n")
        relative = path.relative_to(ctx.workspace).as_posix()
        return RecordResult(fields={"experience_record": relative})


if __name__ == "__main__":
    sdk.main(HyperAgentsRecord, config_schema=CONFIG)
