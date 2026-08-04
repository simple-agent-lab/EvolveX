"""Inject the plugin's candidate-owned context into a Codex session."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    event = json.load(sys.stdin)
    if event.get("hook_event_name") != "SessionStart":
        return 0
    context = (Path(os.environ["PLUGIN_ROOT"]) / "context.md").read_text().strip()
    if not context:
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
