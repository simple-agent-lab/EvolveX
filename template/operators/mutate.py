#!/usr/bin/env python3
"""mutate — change the candidate given dev feedback.

Default at M0: "fixed" variant — a deterministic tweak, no LLM, so the pipeline
idles cheaply. M2 swaps the default to "llm" (claude-agent-sdk reading
meta/mutate.md + top-K playbook insights; injected ids reported as used_insights
for credit backfill). M3+ may also touch operators/ and meta/ (self-reference,
gated by FROZEN/contracts + meta_eval).

Contract: mutates files under candidate/ (M3+: operators/, meta/, program.md);
NEVER writes FROZEN/. Prints JSON {note, predicted_fixes, used_insights, cost}.
"""
import argparse
import json
import os

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", type=int, required=True)
    ap.add_argument("--parent", type=int, required=True)
    a = ap.parse_args()

    # read dev feedback (nominal at M0 — the llm variant actually conditions on it)
    fb_path = os.path.join(WS, "runs", f"gen-{a.gen}", "dev", "feedback.json")
    failed = json.load(open(fb_path)).get("failed_tasks", []) if os.path.exists(fb_path) else []

    params_path = os.path.join(WS, "candidate", "params.json")
    params = json.load(open(params_path))
    params["retries"] = max(0, int(params.get("retries", 0)) + (1 if a.gen % 2 else -1))
    params["temperature"] = round(min(1.0, max(0.0,
        float(params.get("temperature", 0.2)) + (0.05 if a.gen % 3 == 0 else -0.02))), 3)
    params.setdefault("tweak_seq", []).append(a.gen)
    with open(params_path, "w") as f:
        json.dump(params, f, indent=1)

    with open(os.path.join(WS, "candidate", "notes.md"), "a") as f:
        f.write(f"- gen {a.gen} (parent {a.parent}): fixed-mutation, aiming at {len(failed)} failed tasks\n")

    print(json.dumps({
        "note": f"fixed tweak: retries={params['retries']} temperature={params['temperature']}",
        "predicted_fixes": [f"task_{i}" for i in failed[:2]],
        "used_insights": [],
        "cost": {"tokens": 0, "eval_minutes": 0},
    }))


if __name__ == "__main__":
    main()
