#!/usr/bin/env python3
"""mutate — change the candidate given dev feedback.

Default at M0: "fixed" variant — a deterministic tweak, no LLM, so the
pipeline idles cheaply. M2 swaps the default to "llm" (claude-agent-sdk
reading meta/mutate.md + top-K playbook insights; injected ids reported as
used_insights for credit backfill).

Write scope (protocol bound): candidate/ now; operators/, meta/, program.md
open up at M3 behind the contracts + meta_eval admission gates. Never FROZEN/.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import operator_main, read_json, ws_path  # noqa: E402
from FROZEN.contracts.protocol import MutateOutput  # noqa: E402


@operator_main("mutate")
def main(args):
    feedback = read_json(ws_path("runs", f"gen-{args.gen}", "dev", "feedback.json"), {})
    failed = feedback.get("failed_tasks", [])

    params_path = ws_path("candidate", "params.json")
    params = json.loads(params_path.read_text())
    params["retries"] = max(0, int(params.get("retries", 0)) + (1 if args.gen % 2 else -1))
    params["temperature"] = round(min(1.0, max(0.0,
        float(params.get("temperature", 0.2)) + (0.05 if args.gen % 3 == 0 else -0.02))), 3)
    params.setdefault("tweak_seq", []).append(args.gen)
    params_path.write_text(json.dumps(params, indent=1) + "\n")

    with open(ws_path("candidate", "notes.md"), "a") as f:
        f.write(f"- gen {args.gen} (parent {args.parent}): fixed-mutation, "
                f"aiming at {len(failed)} failed tasks\n")

    return MutateOutput(
        note=f"fixed tweak: retries={params['retries']} temperature={params['temperature']}",
        predicted_fixes=[f"task_{i}" for i in failed[:2]],
        used_insights=[],
        cost={"tokens": 0, "eval_minutes": 0},
    )


if __name__ == "__main__":
    main()
